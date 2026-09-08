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
import threading
import urllib.error
import urllib.request
from typing import Callable, Optional

from backend.daemon import launcher

HOST = "127.0.0.1"
REQUEST_TIMEOUT_SECONDS = 120.0  # LLM + tool calls can take a while
EXIT_COMMANDS = {"exit", "quit", "q"}
RESET_COMMANDS = {"reset", "clear", "/reset"}
MODE_COMMANDS = {"mode"}
VALID_MODES = {"learn", "pair-programming", "autonomous"}

# How often the CLI checks the daemon for mode changes made elsewhere
# (e.g. the dashboard) so both directions stay in sync.
MODE_POLL_SECONDS = 2.0
MODE_POLL_TIMEOUT_SECONDS = 5.0


def chat_url(port: int) -> str:
    """Return the daemon's chat endpoint URL for the given port."""
    return f"http://{HOST}:{port}/chat"


def modes_url(port: int) -> str:
    """Return the daemon's modes endpoint URL."""
    return f"http://{HOST}:{port}/modes"


def mode_url(port: int) -> str:
    """Return the daemon's single-mode endpoint URL (GET/POST)."""
    return f"http://{HOST}:{port}/mode"


def fetch_current_mode(port: int, session: str = "default") -> Optional[str]:
    """GET the daemon's stored mode for *session*, or None on any failure."""
    try:
        with urllib.request.urlopen(
            f"{mode_url(port)}?session={session}", timeout=MODE_POLL_TIMEOUT_SECONDS
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
        mode = str(payload.get("mode", "")).strip()
        return mode or None
    except (OSError, ValueError, urllib.error.URLError):
        return None


def push_mode(port: int, mode: str, session: str = "default") -> bool:
    """POST a mode change to the daemon so every client sees it.

    Returns True when the daemon accepted the mode.
    """
    body = json.dumps({"mode": mode, "session": session}).encode("utf-8")
    request = urllib.request.Request(
        mode_url(port),
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=MODE_POLL_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return payload.get("status") == "ok"
    except (OSError, ValueError, urllib.error.URLError):
        return False


def start_mode_poller(
    port: int,
    session: str,
    get_mode: "Callable[[], str]",
    set_mode: "Callable[[str], None]",
) -> threading.Event:
    """Watch the daemon's stored mode and announce changes made elsewhere.

    Runs in a background thread.  When the dashboard (or another client)
    switches the mode, *set_mode* applies it locally and the change is
    printed so the terminal user notices.  Returns a stop event.
    """
    stop = threading.Event()

    def _poll() -> None:
        while not stop.wait(MODE_POLL_SECONDS):
            remote = fetch_current_mode(port, session)
            if remote and remote != get_mode():
                set_mode(remote)
                print(f"(mode changed to: {remote})")

    threading.Thread(target=_poll, daemon=True).start()
    return stop


def send_message(
    port: int,
    message: str,
    workspace: str = "",
    session: str = "default",
    mode: str = "learn",
) -> tuple[str, str, list[dict], str, list[dict]]:
    """POST ``message`` to the daemon's /chat endpoint.

    Returns ``(reply, session_id, concepts, teaching, tool_calls_log)`` so
    the caller can track conversation state and print a trace of the tools
    the agent used.  Concepts themselves are stored for the dashboard, not
    printed here.
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
        payload.get("tool_calls_log", []),
    )


# Label shown per tool in the activity trace.
TOOL_LABELS = {
    "read_file": "Read",
    "write_file": "Wrote",
    "edit_file": "Edited",
    "run_command": "Ran",
}


def _shorten(text: str, limit: int = 60) -> str:
    """Collapse whitespace and truncate *text* to *limit* characters."""
    text = " ".join(text.split())
    if len(text) > limit:
        return text[: limit - 1] + "…"
    return text


def print_activity_trace(tool_calls_log: list[dict]) -> None:
    """Print a summary of the tool calls the coding agent made.

    Each entry looks like ``{"function": {"name", "arguments"}}`` where
    *arguments* is a JSON string.  Entries whose arguments fail to parse
    (e.g. from the text-fallback extractor) are shown without details.
    """
    if not tool_calls_log:
        return
    print("─" * 8 + " agent activity " + "─" * 8)
    for tc in tool_calls_log:
        fn = tc.get("function", {}) or {}
        name = str(fn.get("name", "?"))
        label = TOOL_LABELS.get(name, name)
        try:
            args = json.loads(fn.get("arguments", "") or "{}")
        except (json.JSONDecodeError, TypeError):
            args = None
        if not isinstance(args, dict):
            print(f"  ▸ {label} (no details)")
            continue
        if name in ("read_file", "write_file", "edit_file"):
            detail = _shorten(str(args.get("file_path", "")))
        elif name == "run_command":
            detail = _shorten(str(args.get("command", "")))
        else:
            detail = _shorten(str(fn.get("arguments", "")))
        print(f"  ▸ {label} {detail}")
    print("─" * 24)


NODE_LABELS = {
    "coding_agent": "Coding agent",
    "debug_agent": "Debug agent",
    "assessment_agent": "Assessment agent",
    "teacher_agent": "Teacher agent",
}


def stream_url(port: int) -> str:
    """Return the daemon's streaming chat endpoint URL for the given port."""
    return f"http://{HOST}:{port}/chat/stream"


def _streaming_turn(
    port: int,
    message: str,
    workspace: str,
    session: str,
    mode: str,
) -> Optional[dict]:
    """Send *message* to the daemon's SSE endpoint and print events live.

    Prints ``▸ Read file ✓``-style lines as the agent works.  Returns the
    final ``result`` event payload, or ``None`` when the daemon does not
    offer the streaming endpoint (older daemon → caller should fall back
    to the blocking ``send_message``).
    """
    body = json.dumps(
        {"message": message, "workspace": workspace, "session": session, "mode": mode}
    ).encode("utf-8")
    request = urllib.request.Request(
        stream_url(port),
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    result: Optional[dict] = None
    pending = False  # a tool_start line is open without its ✓/✗ yet
    got_line = False

    def _close_pending() -> None:
        nonlocal pending
        if pending:
            print()
            pending = False

    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
            for raw in resp:
                got_line = True
                line = raw.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                try:
                    event = json.loads(line[5:].strip())
                except json.JSONDecodeError:
                    continue
                etype = event.get("type")
                if etype == "tool_start":
                    _close_pending()
                    tool = str(event.get("tool", "?"))
                    label = TOOL_LABELS.get(tool, tool)
                    print(
                        f"  ▸ {label} {_shorten(str(event.get('detail', '')))}",
                        end="",
                        flush=True,
                    )
                    pending = True
                elif etype == "tool_done":
                    if pending:
                        print(" ✓" if event.get("ok", True) else " ✗")
                        pending = False
                elif etype == "node":
                    _close_pending()
                    node = str(event.get("node", ""))
                    label = NODE_LABELS.get(node, node)
                    if label:
                        print(f"· {label}…")
                elif etype == "status":
                    _close_pending()
                    msg = str(event.get("message", "")).strip()
                    if msg:
                        print(f"  {msg}")
                elif etype == "result":
                    result = event
                elif etype == "error":
                    _close_pending()
                    print(f"(agent error: {event.get('message', 'unknown')})")
    except urllib.error.HTTPError:
        # Endpoint missing (daemon older than this CLI) — use fallback.
        return None
    except (OSError, ValueError) as exc:
        _close_pending()
        if not got_line:
            return None
        print(f"(stream interrupted: {exc})")
        return result
    _close_pending()
    # A completed stream must not be re-run via the fallback — that would
    # execute the same request twice.  Missing ``result`` (e.g. the agent
    # errored) still counts as a finished turn.
    return result if result is not None else {"message": "", "session": session, "concepts": [], "teaching": ""}


def run_session(port: int) -> None:
    """Print the banner and loop until the user exits."""
    import os

    workspace = os.getcwd()
    state = {"session": "default", "mode": fetch_current_mode(port, "default") or "learn"}
    session = state["session"]
    mode = state["mode"]

    print("CodeLith AI — autonomous coding agent")
    print(f"Workspace: {workspace}")
    print(f"Mode: {mode}")
    print("Commands: exit/quit/q to leave, reset/clear to start fresh")
    print("         mode <name> to switch mode (learn, pair-programming, autonomous)")
    print()

    # Keep the terminal in sync with mode changes made on the dashboard:
    # the poller prints "(mode changed to: ...)" when that happens.
    stop_mode_poller = start_mode_poller(
        port,
        session,
        get_mode=lambda: state["mode"],
        set_mode=lambda new: state.__setitem__("mode", new),
    )

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
        # Mode switching (pushed to the daemon so the dashboard sees it too)
        if text.lower().startswith("mode "):
            new_mode = text[5:].strip().lower()
            if new_mode in VALID_MODES:
                if push_mode(port, new_mode, session):
                    state["mode"] = new_mode
                    print(f"(mode: {new_mode})")
                else:
                    print("(could not set mode: daemon unreachable)")
            else:
                print(f"(unknown mode: {new_mode})")
                print(f"(valid modes: {', '.join(sorted(VALID_MODES))})")
            continue
        if text.lower() in MODE_COMMANDS:
            print(f"Current mode: {state['mode']}")
            print(f"Available modes: {', '.join(sorted(VALID_MODES))}")
            continue
        try:
            # Read the current mode at turn start so a dashboard-side switch
            # takes effect on the very next message, even mid-poll.
            mode = fetch_current_mode(port, session) or state["mode"]
            state["mode"] = mode
            result = _streaming_turn(
                port, text, workspace=workspace, session=session, mode=mode
            )
            if result is None:
                # Daemon predates the streaming endpoint — fall back.
                reply, session, _concepts, teaching, tool_calls_log = send_message(
                    port, text, workspace=workspace, session=session, mode=mode
                )
                result = {
                    "message": reply,
                    "session": session,
                    "concepts": _concepts,
                    "teaching": teaching,
                }
                print_activity_trace(tool_calls_log)
        except (OSError, ValueError) as exc:
            print(f"(daemon unreachable: {exc})")
            continue
        reply = result.get("message", "")
        session = result.get("session", session)
        teaching = result.get("teaching", "")
        # Concepts are NOT dumped in the terminal — the daemon persists them
        # and the dashboard polls for them.  The teacher agent's teaching
        # message (printed below, when present) tells the user the concepts
        # are available with explanations on the dashboard.
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
