"""Live event emission for agent activity.

Agent nodes call :func:`emit_event` to report what they are doing while
they are doing it (reading a file, running a command, ...).  The
orchestrator installs a sink via :func:`set_event_sink` before invoking
the graph; the daemon wires the sink to an SSE queue so clients can
watch the agent work in real time.

A ``ContextVar`` carries the sink so nodes can emit events without
plumbing a callback through graph state.  If no sink is installed the
events are simply dropped, so emitting is always safe.
"""

from __future__ import annotations

import time
from contextvars import ContextVar, Token
from typing import Any, Callable

EventSink = Callable[[dict[str, Any]], None]

_event_sink: ContextVar[EventSink | None] = ContextVar(
    "codelith_event_sink", default=None
)


def set_event_sink(sink: EventSink) -> Token:
    """Install *sink* for the current execution context.

    Returns a token to pass to :func:`reset_event_sink` when done.
    """
    return _event_sink.set(sink)


def reset_event_sink(token: Token) -> None:
    """Restore the previous sink for a token from :func:`set_event_sink`."""
    _event_sink.reset(token)


def emit_event(type_: str, **data: Any) -> None:
    """Emit a live activity event to the installed sink, if any.

    Never raises — a broken sink must never take down the agent.
    """
    sink = _event_sink.get()
    if sink is None:
        return
    event = {"type": type_, "ts": time.time(), **data}
    try:
        sink(event)
    except Exception:  # noqa: BLE001 — events are best-effort
        pass
