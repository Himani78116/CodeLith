"""LangGraph orchestrator — wires the user prompt through the agent graph.

Flow:
    User Prompt  →  Coding Agent  →  (if tests fail)  →  Debug Agent  →  END
                       \-> END (tests pass)

The coding agent handles file operations and code generation.  When its
reply indicates test failures, the graph routes to the debug agent which
diagnoses errors, fixes code, and re-runs tests.
"""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from backend.agents.coding_agent import coding_agent_node
from backend.agents.debug_agent import debug_agent_node


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class AgentState(TypedDict):
    """State passed through the graph."""

    messages: Annotated[list[BaseMessage], add_messages]
    workspace_root: str


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

graph_builder = StateGraph(AgentState)

# Nodes
graph_builder.add_node("coding_agent", coding_agent_node)
graph_builder.add_node("debug_agent", debug_agent_node)


# --- Routing logic --------------------------------------------------------
# After the coding agent runs, check whether its last reply indicates
# failing tests.  If so, hand off to the debug agent; otherwise finish.

def _route_after_coding(state: AgentState) -> str:
    """Return 'debug_agent' if tests appear to have failed, else 'end'."""
    msgs = state.get("messages", [])
    if not msgs:
        return "end"
    last = msgs[-1]
    text = last.content if hasattr(last, "content") else str(last)
    lower = text.lower()
    # Heuristic: coding agent signals test failures in its reply.
    fail_signals = ["test failed", "error", "traceback", "failed"]
    if any(sig in lower for sig in fail_signals):
        return "debug_agent"
    return "end"


# Entry point → coding_agent
graph_builder.set_entry_point("coding_agent")

# coding_agent → conditional → debug_agent | END
graph_builder.add_conditional_edges(
    "coding_agent",
    _route_after_coding,
    {"debug_agent": "debug_agent", "end": END},
)

# debug_agent → END (it can loop internally via tool rounds)
graph_builder.add_edge("debug_agent", END)

# Compile once; reused by the daemon.
graph = graph_builder.compile()


# ---------------------------------------------------------------------------
# Convenience runner
# ---------------------------------------------------------------------------

def run_graph(
    user_message: str,
    workspace_root: str | None = None,
    history: list[dict] | None = None,
) -> str:
    """Run the graph with a user message and return the AI reply text.

    Args:
        user_message: The user's prompt.
        workspace_root: Path to the project root for file operations.
            Defaults to the current working directory.
        history: Prior conversation messages as ``[{role, content}, ...]``.
            If provided, they are prepended before the new user message so
            the agent retains context across turns.
    """
    import os

    if workspace_root is None:
        workspace_root = os.getcwd()

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
    }
    result = graph.invoke(initial)
    # The last message should be the AI reply.
    last_msg = result["messages"][-1]
    return last_msg.content if hasattr(last_msg, "content") else str(last_msg)
