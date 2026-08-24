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

from groq import Groq
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
from backend.llm.client import DEFAULT_MODEL, resolve_api_key

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """
You are CodeLith's Debug Agent.  Your job is to find and fix failing tests.

## THE DEBUG LOOP
When you receive test output with errors:
1. **Read the error** — understand what failed and why.
2. **Find the source** — use read_file to look at the failing code.
3. **Diagnose** — identify the root cause (wrong logic, missing import,
   bad syntax, etc.).
4. **Fix** — use edit_file or write_file to correct the code.
5. **Re-run** — use run_command to re-run the tests.
6. **Repeat** until tests pass or you've hit the retry limit.

## YOUR TOOLS
- read_file(file_path)        Read a file's contents.
- write_file(file_path, content)  Create or overwrite a file.
- edit_file(file_path, old_string, new_string)  Targeted find-and-replace.
- run_command(command)         Execute a shell command in the project.

## RULES
- ALWAYS use tools.  Never just describe what's wrong.
- Read the error output carefully before making changes.
- Make the SMALLEST fix that solves the problem.
- After every fix, re-run the tests to verify.
- If you cannot determine the fix after 3 attempts, say so and explain
  what you think is wrong.
- Your FINAL text reply must be SHORT (1-2 sentences).  Say whether
  tests pass now or what the remaining issue is.

## EXAMPLES
User: "Tests are failing: ImportError: No module named 'requests'"
→ read_file('requirements.txt')
→ (if 'requests' missing)
→ write_file('requirements.txt', 'requests\\n')
→ run_command('pip install requests')
→ run_command('pytest')
→ "Added missing 'requests' dependency.  Tests pass now."

User: "Tests fail with AssertionError on line 42"
→ read_file('app.py')
→ (find the bug on line 42)
→ edit_file('app.py', old_line, fixed_line)
→ run_command('pytest')
→ "Fixed off-by-one error.  Tests pass now."
"""

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

    # Tool-use loop — same as coding agent but scoped to debugging.
    for _ in range(MAX_TOOL_ROUNDS):
        completion = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=groq_messages,
            tools=TOOL_DEFINITIONS,
            max_completion_tokens=2048,
        )

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
            groq_messages.append(assistant_msg)

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

                groq_messages.append(
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
    last_msg = groq_messages[-1]
    reply_text = last_msg.get("content", "(debug agent exceeded tool rounds)")
    return {"messages": messages + [AIMessage(content=reply_text)]}
