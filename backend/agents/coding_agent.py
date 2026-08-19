"""Coding Agent — responds to user prompts with file-reading capability.

This agent can now read files from the user's project and use their content
to answer questions, explain code, and help with debugging.  Future phases
will add file-editing and command-running capabilities.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from groq import Groq
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from backend.llm.client import DEFAULT_MODEL, resolve_api_key

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are CodeLith's coding agent. You help users with software "
    "engineering tasks: explaining code, answering questions, debugging, "
    "and planning. You have access to a read_file tool that lets you "
    "read source files from the user's project. Use it when the user "
    "asks you to look at or explain a specific file. Be concise and helpful."
)

# ---------------------------------------------------------------------------
# Tool definitions (Groq / OpenAI function-calling format)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Read the contents of a file in the user's project. "
                "Returns the file content or an error if the file cannot be read."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": (
                            "Path to the file, relative to the project root "
                            "or absolute."
                        ),
                    }
                },
                "required": ["file_path"],
            },
        },
    }
]

# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------

MAX_FILE_SIZE = 100_000  # bytes – guard against huge files


def _read_file(file_path: str, workspace_root: str) -> str:
    """Read *file_path* relative to *workspace_root*.

    Returns the file contents as a string, or an error message if the file
    cannot be read.
    """
    root = Path(workspace_root).resolve()
    target = Path(file_path)

    # If the path is not absolute, resolve it relative to the workspace root.
    if not target.is_absolute():
        target = root / target

    # Safety: ensure the resolved path is still under the workspace root.
    try:
        target = target.resolve()
        if not str(target).startswith(str(root)):
            return f"Error: path '{file_path}' is outside the project root."
    except (OSError, ValueError) as exc:
        return f"Error resolving path: {exc}"

    try:
        size = target.stat().st_size
        if size > MAX_FILE_SIZE:
            return (
                f"Error: file is {size:,} bytes, exceeding the "
                f"{MAX_FILE_SIZE:,} byte limit."
            )
        return target.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return f"Error: file not found: {file_path}"
    except IsADirectoryError:
        return f"Error: '{file_path}' is a directory, not a file."
    except OSError as exc:
        return f"Error reading file: {exc}"


MAX_TOOL_ROUNDS = 5  # prevent infinite loops


# ---------------------------------------------------------------------------
# Agent node
# ---------------------------------------------------------------------------


def coding_agent_node(state: dict[str, Any]) -> dict[str, Any]:
    """LangGraph node: take the latest user message, optionally use tools,
    and produce an AI reply.

    Expects ``state["messages"]`` to be a list of ``BaseMessage`` instances.
    Expects ``state["workspace_root"]`` to be a string path to the project root.
    Returns a dict with the new ``messages`` list (appended AI reply).
    """
    messages: list[BaseMessage] = state.get("messages", [])
    workspace_root: str = state.get("workspace_root", os.getcwd())

    api_key = resolve_api_key()
    if not api_key:
        reply = (
            "I need a Groq API key to think. Set the GROQ_API_KEY "
            "environment variable, or add it to a .env file in the project "
            "root, then try again."
        )
        return {"messages": messages + [AIMessage(content=reply)]}

    client = Groq(api_key=api_key)

    # Build the conversation for Groq.
    groq_messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]
    for msg in messages:
        if isinstance(msg, HumanMessage):
            groq_messages.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AIMessage):
            groq_messages.append({"role": "assistant", "content": msg.content})

    # Tool-use loop: keep calling the LLM until it produces a text reply
    # (no more tool calls) or we hit the round limit.
    for _ in range(MAX_TOOL_ROUNDS):
        completion = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=groq_messages,
            tools=TOOL_DEFINITIONS,
            max_completion_tokens=2048,
        )

        choice = completion.choices[0]
        message = choice.message

        # If the model returned tool calls, execute them and continue the loop.
        if message.tool_calls:
            # Append the assistant message (with tool calls) to the conversation.
            # Strip fields unsupported by Groq (e.g. 'annotations').
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
            groq_messages.append(assistant_msg)

            for tool_call in message.tool_calls:
                fn = tool_call.function
                if fn.name == "read_file":
                    import json

                    try:
                        args = json.loads(fn.arguments)
                    except (json.JSONDecodeError, TypeError):
                        result = "Error: could not parse tool arguments."
                    else:
                        result = _read_file(
                            args.get("file_path", ""),
                            workspace_root,
                        )
                else:
                    result = f"Error: unknown tool '{fn.name}'."

                groq_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result,
                    }
                )
        else:
            # No tool calls — this is the final text reply.
            reply_text = message.content or ""
            return {"messages": messages + [AIMessage(content=reply_text)]}

    # If we exhausted the tool rounds, return whatever we have.
    last_msg = groq_messages[-1]
    reply_text = last_msg.get("content", "(exceeded tool-use rounds)")
    return {"messages": messages + [AIMessage(content=reply_text)]}
