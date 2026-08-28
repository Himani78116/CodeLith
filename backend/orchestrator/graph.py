"""LangGraph orchestrator — wires the user prompt through the agent graph.

Flow:
    User Prompt  →  Coding Agent  →  (if tests fail)  →  Debug Agent  →  Assessment Agent → Teacher Agent → END
                       -> Assessment Agent -> Teacher Agent -> END (tests pass)

The coding agent handles file operations and code generation.  When its
reply indicates test failures, the graph routes to the debug agent which
diagnoses errors, fixes code, and re-runs tests.  The assessment agent
detects concepts used and generates Socratic questions for the dashboard.
The teacher agent saves teaching content to the dashboard and answers
user questions in the terminal.
"""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from backend.agents.coding_agent import coding_agent_node
from backend.agents.debug_agent import debug_agent_node
from backend.agents.assessment_agent import assessment_agent_node
from backend.agents.teacher_agent import teacher_agent_node
from backend.database.concepts import load_concepts, save_concepts_bulk
from backend.orchestrator.modes import get_mode, DEFAULT_MODE


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
    pending_assessments: list[dict]
    # Mode-specific state
    current_mode_config: dict | None


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

graph_builder = StateGraph(AgentState)

# Nodes
graph_builder.add_node("coding_agent", coding_agent_node)
graph_builder.add_node("debug_agent", debug_agent_node)
graph_builder.add_node("assessment_agent", assessment_agent_node)
graph_builder.add_node("teacher_agent", teacher_agent_node)


# --- Routing logic --------------------------------------------------------
# After the coding agent runs, check whether its last reply indicates
# failing tests.  If so, hand off to the debug agent; otherwise go to
# the teacher agent for concept detection.

def _route_after_coding(state: AgentState) -> str:
    """Return 'debug_agent' if tests appear to have failed, else 'assessment_agent'."""
    msgs = state.get("messages", [])
    if not msgs:
        return "assessment_agent"
    last = msgs[-1]
    text = last.content if hasattr(last, "content") else str(last)
    lower = text.lower()
    # Heuristic: coding agent signals test failures in its reply.
    fail_signals = ["test failed", "error", "traceback", "failed"]
    if any(sig in lower for sig in fail_signals):
        return "debug_agent"
    return "assessment_agent"


def _route_after_debug(state: AgentState) -> str:
    """After debug agent, go to assessment agent."""
    return "assessment_agent"


# Entry point → coding_agent
graph_builder.set_entry_point("coding_agent")

# coding_agent → conditional → debug_agent | assessment_agent
graph_builder.add_conditional_edges(
    "coding_agent",
    _route_after_coding,
    {"debug_agent": "debug_agent", "assessment_agent": "assessment_agent"},
)

# debug_agent → assessment_agent
graph_builder.add_conditional_edges(
    "debug_agent",
    _route_after_debug,
    {"assessment_agent": "assessment_agent"},
)

# assessment_agent → teacher_agent
graph_builder.add_edge("assessment_agent", "teacher_agent")

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

    Returns:
        A dict with:
        - "reply": the AI's text reply (coding agent output)
        - "concepts": list of newly detected concepts
        - "teaching": the teacher agent's message (if any)
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
        },
    }
    result = graph.invoke(initial)

    # Extract results
    all_messages = result.get("messages", [])
    new_concepts = result.get("concepts", [])

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

    # Save newly detected concepts
    new_only = [c for c in new_concepts if c["name"] not in {ec["name"] for ec in existing_concepts}]
    if new_only:
        save_concepts_bulk(session, new_only)

    return {
        "reply": coding_reply,
        "concepts": new_only,
        "teaching": teaching_msg,
    }
