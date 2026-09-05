"""Coding Agent — reads and writes files to help users with code.

This agent can read files from the user's project to explain code and
answer questions, and can write or edit files when asked to create,
modify, or refactor code.  Future phases will add command execution
and more advanced capabilities.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from backend.llm.client import DEFAULT_MODEL, resolve_api_key, get_client
from backend.orchestrator.events import emit_event

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are CodeLith, a coding agent. Use tools to read, write, edit files and run commands. ALWAYS use tools, never describe code. Call multiple tools in sequence. Keep final replies short (1-2 sentences).

When asked to run or serve an app:
- For static HTML/CSS/JS files: run `python -m http.server 8080` in the file's directory.
- For Node.js projects: run `npm run dev` or `npx serve`.
- For Python web apps: run `uvicorn <module>:app --reload`.
- Always tell the user the URL (e.g. http://localhost:8080).
- Long-running servers start in the background automatically."""

# ---------------------------------------------------------------------------
# Tool definitions (Groq / OpenAI function-calling format)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file's contents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                },
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or overwrite a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["file_path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Replace text in a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "old_string": {"type": "string"},
                    "new_string": {"type": "string"},
                },
                "required": ["file_path", "old_string", "new_string"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Execute a shell command.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                },
                "required": ["command"],
            },
        },
    }
]

# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------

MAX_FILE_SIZE = 100_000  # bytes – guard against huge files
MAX_WRITE_SIZE = 500_000  # bytes – guard against oversized writes
COMMAND_TIMEOUT = 60  # seconds – prevent hanging commands
BACKGROUND_COMMANDS = {
    "python -m http.server",
    "npx serve",
    "npx http-server",
    "node server",
    "npm run dev",
    "yarn dev",
    "pnpm dev",
    "vite",
    "uvicorn",
}
MAX_OUTPUT_SIZE = 50_000  # chars – guard against huge command output


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


def _write_file(file_path: str, content: str, workspace_root: str) -> str:
    """Write *content* to *file_path* relative to *workspace_root*.

    Creates parent directories as needed.  Returns a confirmation message
    or an error string.
    """
    if len(content.encode("utf-8")) > MAX_WRITE_SIZE:
        return (
            f"Error: content is too large ({len(content):,} chars), "
            f"exceeding the {MAX_WRITE_SIZE:,} byte limit."
        )

    root = Path(workspace_root).resolve()
    target = Path(file_path)

    if not target.is_absolute():
        target = root / target

    try:
        target = target.resolve()
        if not str(target).startswith(str(root)):
            return f"Error: path '{file_path}' is outside the project root."
    except (OSError, ValueError) as exc:
        return f"Error resolving path: {exc}"

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Successfully wrote {len(content):,} chars to {file_path}"
    except OSError as exc:
        return f"Error writing file: {exc}"


def _edit_file(
    file_path: str,
    old_string: str,
    new_string: str,
    workspace_root: str,
) -> str:
    """Replace *old_string* with *new_string* in *file_path*.

    All occurrences of *old_string* are replaced.  Returns a confirmation
    message with the number of replacements, or an error string.
    """
    if not old_string:
        return "Error: old_string must not be empty."

    root = Path(workspace_root).resolve()
    target = Path(file_path)

    if not target.is_absolute():
        target = root / target

    try:
        target = target.resolve()
        if not str(target).startswith(str(root)):
            return f"Error: path '{file_path}' is outside the project root."
    except (OSError, ValueError) as exc:
        return f"Error resolving path: {exc}"

    try:
        original = target.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return f"Error: file not found: {file_path}"
    except IsADirectoryError:
        return f"Error: '{file_path}' is a directory, not a file."
    except OSError as exc:
        return f"Error reading file: {exc}"

    if old_string not in original:
        return (
            f"Error: old_string not found in {file_path}. "
            "Use read_file to get the exact contents first."
        )

    count = original.count(old_string)
    updated = original.replace(old_string, new_string)

    if len(updated.encode("utf-8")) > MAX_WRITE_SIZE:
        return (
            f"Error: result would be too large "
            f"({len(updated):,} chars), exceeding the "
            f"{MAX_WRITE_SIZE:,} byte limit."
        )

    try:
        target.write_text(updated, encoding="utf-8")
        return (
            f"Successfully replaced {count} occurrence(s) in {file_path}."
        )
    except OSError as exc:
        return f"Error writing file: {exc}"


def _is_background_command(command: str) -> bool:
    """Return True if *command* looks like a long-running server process."""
    cmd_lower = command.lower().strip()
    return any(bg in cmd_lower for bg in BACKGROUND_COMMANDS)


def _run_command(command: str, workspace_root: str) -> str:
    """Execute *command* in *workspace_root* and return the combined output.

    Long-running commands (HTTP servers, dev servers) are started in the
    background so they don't block.  Other commands run with a timeout.
    """
    if not command.strip():
        return "Error: command must not be empty."

    # Background long-running commands
    if _is_background_command(command):
        try:
            proc = subprocess.Popen(
                command,
                shell=True,
                cwd=workspace_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            time.sleep(2)
            if proc.poll() is not None:
                stdout, stderr = proc.communicate(timeout=5)
                output = ""
                if stdout:
                    output += stdout.decode("utf-8", errors="replace")
                if stderr:
                    output += ("\n" if output else "") + stderr.decode("utf-8", errors="replace")
                if not output:
                    output = "(no output)"
                return output + f"\n(exit code: {proc.returncode})"
            else:
                return (
                    f"Server started in background (pid: {proc.pid}). "
                    f"It will keep running until you stop it."
                )
        except OSError as exc:
            return f"Error starting background process: {exc}"

    # Regular commands with timeout
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=workspace_root,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return (
            f"Error: command timed out after {COMMAND_TIMEOUT}s. "
            "The command may be hanging."
        )
    except OSError as exc:
        return f"Error running command: {exc}"

    # Combine stdout and stderr.
    output = ""
    if result.stdout:
        output += result.stdout
    if result.stderr:
        output += ("\n" if output else "") + result.stderr

    if not output:
        output = "(no output)"

    # Truncate if too large.
    if len(output) > MAX_OUTPUT_SIZE:
        output = output[:MAX_OUTPUT_SIZE] + "\n... (output truncated)"

    # Append exit code.
    output += f"\n(exit code: {result.returncode})"
    return output


MAX_TOOL_ROUNDS = 5  # prevent infinite loops


def _parse_tool_args(raw_arguments: str) -> dict[str, Any]:
    """Parse a tool-call arguments JSON string, returning {} on failure."""
    try:
        parsed = json.loads(raw_arguments)
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _describe_tool(name: str, args: dict[str, Any]) -> str:
    """Return a short human-readable detail line for a tool call."""
    if name in ("read_file", "write_file", "edit_file"):
        return str(args.get("file_path", ""))
    if name == "run_command":
        return str(args.get("command", ""))
    return json.dumps(args)[:120]


def _execute_tool(name: str, args: dict[str, Any], workspace_root: str) -> str:
    """Execute a single tool by name and return its result string."""
    if name == "read_file":
        return _read_file(args.get("file_path", ""), workspace_root)
    if name == "write_file":
        return _write_file(
            args.get("file_path", ""),
            args.get("content", ""),
            workspace_root,
        )
    if name == "edit_file":
        return _edit_file(
            args.get("file_path", ""),
            args.get("old_string", ""),
            args.get("new_string", ""),
            workspace_root,
        )
    if name == "run_command":
        return _run_command(args.get("command", ""), workspace_root)
    return f"Error: unknown tool '{name}'."


# ---------------------------------------------------------------------------
# Text-based tool extraction fallback
# ---------------------------------------------------------------------------

def _extract_tool_calls_from_text(text: str) -> list[dict[str, Any]]:
    """Parse tool calls from plain text when the model doesn't use the tool API.

    Looks for patterns like:
        tool_name(arg1, arg2)
        tool_name("arg1", "arg2")
    """
    tool_calls: list[dict[str, Any]] = []

    # Match patterns like: function_name(args)
    pattern = r'\b(read_file|write_file|edit_file|run_command)\s*\((.+?)\)\s*(?:\n|$)'
    matches = re.findall(pattern, text, re.DOTALL)

    for tool_name, raw_args in matches:
        # Parse arguments
        args_str = raw_args.strip()
        try:
            # Try JSON-style first
            if args_str.startswith('{'):
                args = json.loads(args_str)
            elif '"' in args_str or "'" in args_str:
                # Extract quoted strings
                parts = re.findall(r'["\'](.+?)["\']', args_str)
                if tool_name == 'read_file' and parts:
                    args = {'file_path': parts[0]}
                elif tool_name == 'write_file' and len(parts) >= 2:
                    args = {'file_path': parts[0], 'content': parts[1]}
                elif tool_name == 'edit_file' and len(parts) >= 3:
                    args = {'file_path': parts[0], 'old_string': parts[1], 'new_string': parts[2]}
                elif tool_name == 'run_command' and parts:
                    args = {'command': parts[0]}
                else:
                    args = {}
            else:
                # Bare arguments
                if tool_name in ('read_file', 'run_command'):
                    args = {'file_path': args_str} if tool_name == 'read_file' else {'command': args_str}
                else:
                    args = {}
        except (json.JSONDecodeError, TypeError):
            args = {}

        tool_calls.append({
            'function': {
                'name': tool_name,
                'arguments': json.dumps(args),
            }
        })

    return tool_calls


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

    # Collect tool calls for the teacher agent to analyze
    all_tool_calls: list[dict[str, Any]] = []

    # Tool-use loop: keep calling the LLM until it produces a text reply
    # (no more tool calls) or we hit the round limit.
    for _ in range(MAX_TOOL_ROUNDS):
        emit_event("status", message="Thinking…")
        try:
            completion = client.chat.completions.create(
                model=DEFAULT_MODEL,
                messages=api_messages,
                tools=TOOL_DEFINITIONS,
                max_completion_tokens=2048,
            )
        except Exception as exc:
            reply_text = f"(LLM error: {exc})"
            return {
                "messages": messages + [AIMessage(content=reply_text)],
                "tool_calls_log": all_tool_calls,
            }

        choice = completion.choices[0]
        message = choice.message

        # Track tool calls for the teacher agent
        if message.tool_calls:
            for tc in message.tool_calls:
                all_tool_calls.append({
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    }
                })

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
            api_messages.append(assistant_msg)

            for tool_call in message.tool_calls:
                fn = tool_call.function
                args = _parse_tool_args(fn.arguments)
                detail = _describe_tool(fn.name, args)
                emit_event("tool_start", tool=fn.name, detail=detail)
                result = _execute_tool(fn.name, args, workspace_root)
                emit_event(
                    "tool_done",
                    tool=fn.name,
                    detail=detail,
                    ok=not str(result).startswith("Error"),
                )

                api_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result,
                    }
                )
        else:
            # No tool calls — try text-based extraction as fallback
            reply_text = message.content or ""
            fallback_calls = _extract_tool_calls_from_text(reply_text)
            if fallback_calls:
                # Found tool calls in text — execute them
                for fc in fallback_calls:
                    all_tool_calls.append(fc)
                    fn_name = fc["function"]["name"]
                    args = _parse_tool_args(fc["function"].get("arguments", ""))
                    detail = _describe_tool(fn_name, args)
                    emit_event("tool_start", tool=fn_name, detail=detail)
                    result = _execute_tool(fn_name, args, workspace_root)
                    emit_event(
                        "tool_done",
                        tool=fn_name,
                        detail=detail,
                        ok=not str(result).startswith("Error"),
                    )
                    api_messages.append({"role": "assistant", "content": f"{fn_name}({args})"})
                    api_messages.append({"role": "tool", "tool_call_id": f"text_{fn_name}", "content": result})
                # Continue loop — the next LLM call will see the results
                continue
            # No tool calls found — return as final reply
            return {
                "messages": messages + [AIMessage(content=reply_text)],
                "tool_calls_log": all_tool_calls,
            }

    # If we exhausted the tool rounds, return whatever we have.
    last_msg = api_messages[-1]
    reply_text = last_msg.get("content", "(exceeded tool-use rounds)")
    return {
        "messages": messages + [AIMessage(content=reply_text)],
        "tool_calls_log": all_tool_calls,
    }
