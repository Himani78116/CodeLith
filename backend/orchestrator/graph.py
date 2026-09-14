"""LangGraph orchestrator — wires the user prompt through the agent graph.

Flow:
    User Prompt → Coding Agent → (if tests fail) → Debug Agent ┐
                        └─ (tests pass) ───────────────────────┤
                                                               ▼
                                                     Detect Concepts
                                                               │
                                              ┌────────────────┴──────────────┐
                                              ▼                               ▼
                                     Assessment Agent                Teacher Agent → END
                                       (mode-gated)

The coding agent handles file operations and code generation.  When one
of its commands actually fails (non-zero exit code or stderr output,
read from the structured ``tool_calls_log`` entries), the graph routes
to the debug agent which diagnoses errors, fixes code, and re-runs
tests.  The shared detect_concepts
node then runs concept detection ONCE per turn (registry scan + mode-gated
LLM detection) and writes the result to ``concepts_detected``.  The
assessment agent generates Socratic questions for the dashboard and the
teacher agent saves teaching content to the dashboard; both read the
shared detection result instead of re-scanning tool calls.
"""

from __future__ import annotations

from typing import Annotated, Any, Callable, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from backend.agents.concept_detector import detect_concepts
from backend.agents.coding_agent import coding_agent_node

from backend.agents.debug_agent import debug_agent_node
from backend.agents.assessment_agent import assessment_agent_node
from backend.agents.teacher_agent import teacher_agent_node
from backend.database.concepts import load_concepts, save_concepts_bulk
from backend.orchestrator.modes import get_mode, DEFAULT_MODE
from backend.orchestrator.events import emit_event, set_event_sink, reset_event_sink


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class AgentState(TypedDict):
    """State passed through the graph."""

    messages: Annotated[list[BaseMessage], add_messages]
    workspace_root: str
    mode: str
    session: str
    tool_calls_log: list[dict]
    concepts: list[dict]
    # Written by the detect_concepts node each turn: newly detected
    # concepts as dicts with name/category/description/diagram (+
    # source_file/line_range).  Read by the assessment and teacher agents.
    concepts_detected: list[dict]
    pending_assessments: list[dict]
    # Set by the coding agent when the turn failed on a provider-side LLM
    # error (not a code problem) so the debug agent can be skipped.
    llm_error: bool
    # Mode-specific state
    current_mode_config: dict | None


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

graph_builder = StateGraph(AgentState)

# Nodes — each is wrapped to emit a live "node" event when it starts,
# so stream consumers can see which agent is running.

def _traced(name: str, fn: Callable[[dict], dict]) -> Callable[[dict], dict]:
    """Wrap a graph node so it emits a ``node`` event when it begins."""

    def wrapped(state: dict) -> dict:
        emit_event("node", node=name)
        return fn(state)

    return wrapped


graph_builder.add_node("coding_agent", _traced("coding_agent", coding_agent_node))
graph_builder.add_node("debug_agent", _traced("debug_agent", debug_agent_node))
graph_builder.add_node(
    "detect_concepts", _traced("detect_concepts", detect_concepts)
)
graph_builder.add_node("assessment_agent", _traced("assessment_agent", assessment_agent_node))
graph_builder.add_node("teacher_agent", _traced("teacher_agent", teacher_agent_node))


# --- Routing logic --------------------------------------------------------
# After the coding agent runs, inspect the turn's structured tool results.
# The most recent run_command result decides: non-zero exit code or stderr
# hands off to the debug agent; either way the next stop is the shared
# detect_concepts node.

def _route_after_coding(state: AgentState) -> str:
    """Route to ``debug_agent`` when the latest command actually failed.

    Only the most recent ``run_command`` entry in ``tool_calls_log`` is
    consulted: an earlier failing command that the coding agent already
    re-ran cleanly is a self-corrected turn, not a job for the debug
    agent.  The latest command failed when it recorded
    ``exit_code != 0`` or ``stderr_present``.  The routing decision is
    based purely on these structured execution results — the coding
    agent's reply text is never keyword-scanned, so a clean reply that
    merely mentions a word such as error cannot trigger the debug agent.
    """
    # A provider-side LLM failure is not a code problem — routing to the
    # debug agent would burn another LLM call trying to "fix" a glitch.
    if state.get("llm_error"):
        return "detect_concepts"
    tool_calls_log = state.get("tool_calls_log") or []
    last_command: dict | None = None
    for entry in tool_calls_log:
        if (entry.get("function") or {}).get("name") == "run_command":
            last_command = entry
    if last_command is not None:
        exit_code = last_command.get("exit_code", 0)
        stderr_present = last_command.get("stderr_present", False)
        if exit_code != 0 or stderr_present:
            return "debug_agent"
    return "detect_concepts"


def _route_after_debug(state: AgentState) -> str:
    """After debug agent, go to the shared concept-detection node."""
    return "detect_concepts"


# Entry point → coding_agent
graph_builder.set_entry_point("coding_agent")

# coding_agent → conditional → debug_agent | assessment_agent
graph_builder.add_conditional_edges(
    "coding_agent",
    _route_after_coding,
    {"debug_agent": "debug_agent", "detect_concepts": "detect_concepts"},
)

# debug_agent → detect_concepts
graph_builder.add_conditional_edges(
    "debug_agent",
    _route_after_debug,
    {"detect_concepts": "detect_concepts"},
)

def _route_after_detect(state: AgentState) -> str:
    """Skip the assessment agent when the mode disables questions."""
    if (state.get("current_mode_config") or {}).get(
        "assessment_frequency", "high"
    ) == "none":
        return "end"
    return "assessment_agent"


def _route_after_assessment(state: AgentState) -> str:
    """Run the teacher agent in modes where it always runs."""
    if (state.get("current_mode_config") or {}).get("teacher_always_runs", True):
        return "teacher_agent"
    return "end"


# detect_concepts → conditional → assessment_agent | END
# (assessment agent is skipped when the mode disables questions; the
# teacher agent always gets the shared concepts_detected result)
graph_builder.add_conditional_edges(
    "detect_concepts",
    _route_after_detect,
    {"assessment_agent": "assessment_agent", "end": END},
)

# assessment_agent → conditional → teacher_agent | END
# (teacher agent is skipped in modes where it doesn't always run)
graph_builder.add_conditional_edges(
    "assessment_agent",
    _route_after_assessment,
    {"teacher_agent": "teacher_agent", "end": END},
)

# teacher_agent → END
graph_builder.add_edge("teacher_agent", END)

# Compile once; reused by the daemon.
graph = graph_builder.compile()


# ---------------------------------------------------------------------------
# Convenience runner
# ---------------------------------------------------------------------------

def run_graph(
    user_message: str,
    workspace_root: str | None = None,
    history: list[dict] | None = None,
    mode: str = DEFAULT_MODE,
    session: str = "default",
    event_sink: Callable[[dict], None] | None = None,
) -> dict:
    """Run the graph with a user message and return the result dict.

    Args:
        user_message: The user's prompt.
        workspace_root: Path to the project root for file operations.
            Defaults to the current working directory.
        history: Prior conversation messages as ``[{role, content}, ...]``.
            If provided, they are prepended before the new user message so
            the agent retains context across turns.
        mode: Session mode ("learn", "pair-programming", "autonomous").
        session: Session id for concept storage.
        event_sink: Optional callback invoked with live activity event dicts
            (``{"type": ..., ...}``) while the graph runs — used by the
            daemon to stream progress to the CLI/dashboard.  Events are
            emitted as the coding agent reads/writes/executes.

    Returns:
        A dict with:
        - "reply": the AI's text reply (coding agent output)
        - "concepts": list of newly detected concepts
        - "teaching": the teacher agent's message (if any)
        - "tool_calls_log": tool calls made by the coding agent,
          each ``{"function": {"name", "arguments"}}``
    """
    import os

    if workspace_root is None:
        workspace_root = os.getcwd()

    mode_config = get_mode(mode)

    # Load existing concepts for this session
    existing_concepts = load_concepts(session)

    # Build the initial message list.
    messages: list[BaseMessage] = []
    if history:
        for entry in history:
            if entry["role"] == "user":
                messages.append(HumanMessage(content=entry["content"]))
            elif entry["role"] == "assistant":
                messages.append(AIMessage(content=entry["content"]))
    messages.append(HumanMessage(content=user_message))

    initial: AgentState = {
        "messages": messages,
        "workspace_root": workspace_root,
        "mode": mode,
        "session": session,
        "tool_calls_log": [],
        "concepts": existing_concepts,
        "pending_assessments": [],
        "current_mode_config": {
            "name": mode_config.name,
            "teacher_always_runs": mode_config.teacher_always_runs,
            "agent_explains": mode_config.agent_explains,
            "llm_detection": mode_config.llm_detection,
            "surface_concepts": mode_config.surface_concepts,
            "max_tool_rounds": mode_config.max_tool_rounds,
            "prompt_suffix": mode_config.prompt_suffix,
            "assessment_frequency": mode_config.assessment_frequency,
        },
    }
    # Install the event sink for this graph run so nodes can emit live
    # activity events (see backend/orchestrator/events.py).
    if event_sink is None:
        result = graph.invoke(initial)
    else:
        token = set_event_sink(event_sink)
        try:
            result = graph.invoke(initial)
        finally:
            reset_event_sink(token)

    # Extract results
    all_messages = result.get("messages", [])
    new_concepts = result.get("concepts", [])
    tool_calls_log = result.get("tool_calls_log", [])

    # Find the coding agent's reply and teaching message
    coding_reply = ""
    teaching_msg = ""
    for msg in all_messages:
        if hasattr(msg, "content"):
            text = msg.content if isinstance(msg.content, str) else str(msg.content)
            # The first AI message after user input is the coding agent's reply
            if isinstance(msg, AIMessage) and not coding_reply:
                coding_reply = text
            elif isinstance(msg, AIMessage) and coding_reply and not teaching_msg:
                teaching_msg = text
                break

    # Save newly detected concepts (dedup by concept identity slug,
    # falling back to name comparison for legacy entries without one)
    existing_names = {ec["name"] for ec in existing_concepts}
    existing_slugs = {ec.get("slug") for ec in existing_concepts if ec.get("slug")}
    new_only = [
        c for c in new_concepts
        if c["name"] not in existing_names
        and c.get("slug", "") not in existing_slugs
    ]
    if new_only:
        save_concepts_bulk(session, new_only)

    return {
        "reply": coding_reply,
        "concepts": new_only,
        "teaching": teaching_msg,
        "tool_calls_log": tool_calls_log,
    }
