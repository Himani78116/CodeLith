"""LangGraph orchestrator — wires the user prompt to the coding agent.

Flow:
    User Prompt  →  LangGraph  →  Coding Agent (respond only)

The graph is intentionally minimal right now: a single node that forwards
the conversation to the coding agent and returns its reply. Tool-use loops,
file-editing nodes, and routing logic will be layered on in later phases.
"""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from backend.agents.coding_agent import coding_agent_node


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class AgentState(TypedDict):
    """State passed through the graph."""

    messages: Annotated[list[BaseMessage], add_messages]


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

def run_graph(user_message: str) -> str:
    """Run the graph with a single user message and return the AI reply text."""
    initial: AgentState = {
        "messages": [HumanMessage(content=user_message)],
    }
    result = graph.invoke(initial)
    # The last message should be the AI reply.
    last_msg = result["messages"][-1]
    return last_msg.content if hasattr(last_msg, "content") else str(last_msg)
