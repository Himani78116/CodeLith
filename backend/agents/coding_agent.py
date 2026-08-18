"""Coding Agent — responds to user prompts without editing files.

This is the initial implementation where the agent only generates text
replies. File-editing capabilities will be added later.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool

from backend.llm.client import generate_reply

SYSTEM_PROMPT = (
    "You are CodeLith's coding agent. You help users with software "
    "engineering tasks: explaining concepts, answering questions, debugging, "
    "and planning. Right now you can only respond — you cannot edit files or "
    "run commands. Be concise and helpful."
)


@tool
def respond_to_user(prompt: str) -> str:
    """Generate a response to the user's prompt.

    Args:
        prompt: The user's question or request.

    Returns:
        The agent's text response.
    """
    return generate_reply(prompt)


def coding_agent_node(state: dict[str, Any]) -> dict[str, Any]:
    """LangGraph node: take the latest user message and produce an AI reply.

    Expects ``state["messages"]`` to be a list of ``BaseMessage`` instances.
    Returns a dict with the new ``messages`` list (appended AI reply).
    """
    messages: list[BaseMessage] = state.get("messages", [])

    # Build a single prompt from the conversation so far.
    # We pass the full history to generate_reply which only supports a
    # single user message, so we concatenate into one prompt.
    user_parts: list[str] = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            user_parts.append(f"User: {msg.content}")
        elif isinstance(msg, AIMessage):
            user_parts.append(f"Assistant: {msg.content}")
        elif isinstance(msg, SystemMessage):
            user_parts.append(f"System: {msg.content}")

    combined = "\n".join(user_parts) if user_parts else ""

    reply_text = generate_reply(combined)

    return {"messages": messages + [AIMessage(content=reply_text)]}
