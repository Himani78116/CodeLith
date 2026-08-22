"""LangGraph orchestrator — wires the user prompt to the coding agent.

Flow:
    User Prompt  →  LangGraph  →  Coding Agent (read + respond)

The graph is intentionally minimal right now: a single node that forwards
the conversation to the coding agent and returns its reply.  File-editing
nodes and routing logic will be layered on in later phases.
"""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from backend.agents.coding_agent import coding_agent_node


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

# Single node for now — the coding agent.
graph_builder.add_node("coding_agent", coding_agent_node)

# Entry point → coding_agent → END
graph_builder.set_entry_point("coding_agent")
graph_builder.add_edge("coding_agent", END)

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
