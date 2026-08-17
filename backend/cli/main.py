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
REQUEST_TIMEOUT_SECONDS = 10.0
EXIT_COMMANDS = {"exit", "quit", "q"}


def chat_url(port: int) -> str:
    """Return the daemon's chat endpoint URL for the given port."""
    return f"http://{HOST}:{port}/chat"


def send_message(port: int, message: str) -> str:
    """POST ``message`` to the daemon's /chat endpoint and return its reply."""
    body = json.dumps({"message": message}).encode("utf-8")
    request = urllib.request.Request(
        chat_url(port),
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return str(payload.get("message", ""))


def run_session(port: int) -> None:
    """Print the banner and loop until the user exits."""
    print("Mentor AI")
    print("Mode: Learn")
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
        try:
            reply = send_message(port, text)
        except (OSError, ValueError) as exc:
            print(f"(daemon unreachable: {exc})")
            continue
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
