"""Mentor CLI: an interactive session that talks to the local daemon.

The CLI makes sure the daemon is running (starting it as a detached process if
needed — see ``backend.daemon.launcher``), then relays every line the user
types to the daemon's ``POST /chat`` endpoint and prints the reply. When the
CLI exits, the daemon keeps running in the background.

Run it from the repo root with::

    python -m backend.cli.main

or, after ``pip install -e .``::

    mentor
"""

from __future__ import annotations

import json
import sys
import urllib.request
from typing import Optional

from backend.daemon import launcher

HOST = "127.0.0.1"
REQUEST_TIMEOUT_SECONDS = 120.0  # LLM + tool calls can take a while
EXIT_COMMANDS = {"exit", "quit", "q"}
RESET_COMMANDS = {"reset", "clear", "/reset"}
MODE_COMMANDS = {"mode"}
VALID_MODES = {"learn", "pair-programming", "autonomous"}


def chat_url(port: int) -> str:
    """Return the daemon's chat endpoint URL for the given port."""
    return f"http://{HOST}:{port}/chat"


def modes_url(port: int) -> str:
    """Return the daemon's modes endpoint URL."""
    return f"http://{HOST}:{port}/modes"


def send_message(
    port: int,
    message: str,
    workspace: str = "",
    session: str = "default",
    mode: str = "learn",
) -> tuple[str, str, list[dict], str]:
    """POST ``message`` to the daemon's /chat endpoint.

    Returns ``(reply, session_id, concepts, teaching)`` so the caller can
    track conversation state and show concepts.
    """
    body = json.dumps(
        {"message": message, "workspace": workspace, "session": session, "mode": mode}
    ).encode("utf-8")
    request = urllib.request.Request(
        chat_url(port),
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return (
        str(payload.get("message", "")),
        str(payload.get("session", session)),
        payload.get("concepts", []),
        payload.get("teaching", ""),
    )


def run_session(port: int) -> None:
    """Print the banner and loop until the user exits."""
    import os

    workspace = os.getcwd()
    session = "default"
    mode = "learn"

    print("CodeLith AI — autonomous coding agent")
    print(f"Workspace: {workspace}")
    print(f"Mode: {mode}")
    print("Commands: exit/quit/q to leave, reset/clear to start fresh")
    print("         mode <name> to switch mode (learn, pair-programming, autonomous)")
    print()
    while True:
        try:
            line = input("> ")
        except EOFError:
            print()
            break
        text = line.strip()
        if not text:
            continue
        if text.lower() in EXIT_COMMANDS:
            break
        if text.lower() in RESET_COMMANDS:
            session = "default"
            print("(conversation reset)")
            continue
        # Mode switching
        if text.lower().startswith("mode "):
            new_mode = text[5:].strip().lower()
            if new_mode in VALID_MODES:
                mode = new_mode
                print(f"(mode: {mode})")
            else:
                print(f"(unknown mode: {new_mode})")
                print(f"(valid modes: {', '.join(sorted(VALID_MODES))})")
            continue
        if text.lower() in MODE_COMMANDS:
            print(f"Current mode: {mode}")
            print(f"Available modes: {', '.join(sorted(VALID_MODES))}")
            continue
        try:
            reply, session, concepts, teaching = send_message(
                port, text, workspace=workspace, session=session, mode=mode
            )
        except (OSError, ValueError) as exc:
            print(f"(daemon unreachable: {exc})")
            continue
        # Show concepts if new ones were detected
        if concepts:
            print()
            for c in concepts:
                print(f"  📚 {c.get('name', '?')} ({c.get('category', '?')})")
                if c.get('description'):
                    print(f"     {c['description'][:100]}")
            print()
        # Show teaching message
        if teaching:
            print(teaching)
        print(reply)


def main() -> int:
    """Ensure the daemon is running, then start the interactive session."""
    # Windows consoles default to cp1252 and raise UnicodeEncodeError on
    # non-Latin-1 output; LLM replies can contain emoji or other Unicode,
    # so force UTF-8 and replace any undisplayable characters.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    try:
        _, port, _ = launcher.start()
    except SystemExit as exc:
        print(f"Could not start the daemon: {exc}", file=sys.stderr)
        return 1
    try:
        run_session(port)
    except KeyboardInterrupt:
        print()
    print("Session ended - the daemon keeps running in the background.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
