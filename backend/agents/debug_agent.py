"""Debug Agent — runs tests, reads errors, fixes code, re-runs.

This agent is invoked when tests fail.  It enters a loop:

    Run tests → read error → fix code → run tests → repeat

It uses the same tool infrastructure as the coding agent (read_file,
write_file, edit_file, run_command) but has a tighter system prompt
focused on debugging and a capped retry count to avoid infinite loops.
"""

from __future__ import annotations

import json
import os
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from backend.agents.coding_agent import (
    MAX_OUTPUT_SIZE,
    MAX_TOOL_ROUNDS,
    MAX_WRITE_SIZE,
    COMMAND_TIMEOUT,
    TOOL_DEFINITIONS,
    _read_file,
    _write_file,
    _edit_file,
    _run_command,
)
from backend.llm.client import DEFAULT_MODEL, resolve_api_key, get_client

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a debug agent. Fix failing tests. Read the error, find the source, fix it, re-run tests. Use tools. Keep replies short."""

# ---------------------------------------------------------------------------
# Debug-specific constants
# ---------------------------------------------------------------------------

MAX_DEBUG_RETRIES = 3  # max fix attempts before giving up


# ---------------------------------------------------------------------------
# Agent node
# ---------------------------------------------------------------------------


def debug_agent_node(state: dict[str, Any]) -> dict[str, Any]:
    """LangGraph node: run tests, diagnose failures, fix code, re-run.

    Expects ``state["messages"]`` to contain the prior conversation (the
    coding agent's work and the test output that triggered this node).
    Expects ``state["workspace_root"]`` to be a string path.

    Returns updated ``messages`` with the debug agent's reply.
    """
    messages: list[BaseMessage] = state.get("messages", [])
    workspace_root: str = state.get("workspace_root", os.getcwd())

    api_key = resolve_api_key()
    if not api_key:
        reply = (
            "Debug agent needs a Groq API key. Set GROQ_API_KEY "
            "environment variable and try again."
        )
        return {"messages": messages + [AIMessage(content=reply)]}

    try:
        client = get_client()
    except ValueError as exc:
        return {"messages": messages + [AIMessage(content=str(exc))]}

    # Build the conversation.
    api_messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]
    for msg in messages:
        if isinstance(msg, HumanMessage):
            api_messages.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AIMessage):
            api_messages.append({"role": "assistant", "content": msg.content})

    # Tool-use loop — same as coding agent but scoped to debugging.
    for _ in range(MAX_TOOL_ROUNDS):
        try:
            completion = client.chat.completions.create(
                model=DEFAULT_MODEL,
                messages=api_messages,
                tools=TOOL_DEFINITIONS,
                max_completion_tokens=2048,
            )
        except Exception as exc:
            reply_text = f"(LLM error: {exc})"
            return {"messages": messages + [AIMessage(content=reply_text)]}

        choice = completion.choices[0]
        message = choice.message

        if message.tool_calls:
            assistant_msg: dict[str, Any] = {
                "role": "assistant",
                "content": message.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in message.tool_calls
                ],
            }
            api_messages.append(assistant_msg)

            for tool_call in message.tool_calls:
                fn = tool_call.function

                try:
                    args = json.loads(fn.arguments)
                except (json.JSONDecodeError, TypeError):
                    result = "Error: could not parse tool arguments."
                else:
                    if fn.name == "read_file":
                        result = _read_file(
                            args.get("file_path", ""),
                            workspace_root,
                        )
                    elif fn.name == "write_file":
                        result = _write_file(
                            args.get("file_path", ""),
                            args.get("content", ""),
                            workspace_root,
                        )
                    elif fn.name == "edit_file":
                        result = _edit_file(
                            args.get("file_path", ""),
                            args.get("old_string", ""),
                            args.get("new_string", ""),
                            workspace_root,
                        )
                    elif fn.name == "run_command":
                        result = _run_command(
                            args.get("command", ""),
                            workspace_root,
                        )
                    else:
                        result = f"Error: unknown tool '{fn.name}'."

                api_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result,
                    }
                )
        else:
            # No tool calls — final text reply.
            reply_text = message.content or ""
            return {"messages": messages + [AIMessage(content=reply_text)]}

    # Exhausted tool rounds.
    last_msg = api_messages[-1]
    reply_text = last_msg.get("content", "(debug agent exceeded tool rounds)")
    return {"messages": messages + [AIMessage(content=reply_text)]}
