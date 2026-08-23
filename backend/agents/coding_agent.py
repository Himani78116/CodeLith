"""Coding Agent — reads and writes files to help users with code.

This agent can read files from the user's project to explain code and
answer questions, and can write or edit files when asked to create,
modify, or refactor code.  Future phases will add command execution
and more advanced capabilities.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from groq import Groq
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from backend.llm.client import DEFAULT_MODEL, resolve_api_key

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """
You are CodeLith, an autonomous coding agent. You write, create, and
edit real files in the user's project. You do NOT just talk about
code — you produce it.

## YOUR TOOLS
- read_file(file_path)        Read a file's contents.
- write_file(file_path, content)  Create or overwrite a file.
- edit_file(file_path, old_string, new_string)  Targeted find-and-replace.
- run_command(command)         Execute a shell command in the project.

## HOW TO THINK
When the user asks you to do something:
1. Break the task into concrete file operations.
2. If you need to understand existing code, read it first.
3. Create or edit files to implement the solution.
4. If the task needs dependencies or build steps, run_command to install
   or build.
5. Run tests with run_command to verify your work.
6. Confirm what you did.

## RULES
- ALWAYS use tools. NEVER just describe code in a code block.
- For new files: call write_file immediately with the full content.
- For edits: read_file first to get the exact text, then edit_file.
- For setup: run_command to install deps (npm install, pip install, etc).
- For testing: run_command to run tests (npm test, pytest, etc).
- You can call multiple tools in sequence.
- Be confident. You are the coder, not a tutor.
- If a task is large, break it into multiple files and create them one
  by one.
- After creating project files, install dependencies and run tests to
  verify everything works.
- Your FINAL text reply must be SHORT (1-2 sentences). Say what you
  created/edited. Do NOT include code snippets, code blocks, or file
  contents in your reply — the files already exist on disk.

## EXAMPLES
User: "create a Python script that prints hello world"
→ write_file('hello.py', 'print("Hello, world!")')
→ run_command('python hello.py')
→ "Created hello.py and verified it runs."

User: "set up a Node.js Express project"
→ write_file('package.json', '{"name": "myapp", ...}')
→ write_file('index.js', 'const express = require("express")...')
→ run_command('npm install')
→ run_command('node index.js')
→ "Created Express project and installed dependencies."

User: "run the tests"
→ run_command('npm test')
→ "Tests passed." or "3 tests failed — here's what's wrong..."

User: "check git status"
→ run_command('git status')
→ "You have 2 modified files and 1 untracked file."
"""

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
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": (
                "Create or overwrite a file in the user's project. "
                "Creates parent directories if needed. "
                "Returns a success message or an error."
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
                    },
                    "content": {
                        "type": "string",
                        "description": "The full content to write to the file.",
                    },
                },
                "required": ["file_path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": (
                "Replace all occurrences of old_string with new_string "
                "inside an existing file. Use read_file first to get "
                "the exact text to replace. Returns a success message "
                "or an error."
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
                    },
                    "old_string": {
                        "type": "string",
                        "description": (
                            "The exact text to find and replace. Must match "
                            "the file contents exactly."
                        ),
                    },
                    "new_string": {
                        "type": "string",
                        "description": "The replacement text.",
                    },
                },
                "required": ["file_path", "old_string", "new_string"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": (
                "Execute a shell command in the user's project directory. "
                "Returns stdout+stderr or an error. Use for npm install, "
                "pytest, git status, python main.py, etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": (
                            "The shell command to execute, e.g. "
                            "'npm install' or 'pytest'."
                        ),
                    },
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


def _run_command(command: str, workspace_root: str) -> str:
    """Execute *command* in *workspace_root* and return the combined output.

    Runs with a timeout and output size limit.  Returns a string with
    stdout, stderr, and exit code.
    """
    if not command.strip():
        return "Error: command must not be empty."

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
                import json

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
