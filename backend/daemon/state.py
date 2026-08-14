from __future__ import annotations

import os
from pathlib import Path

STATE_DIR_NAME = ".mentor"
PID_FILE_NAME = "daemon.pid"
PORT_FILE_NAME = "daemon.port"

PID_FILE = Path.home() / STATE_DIR_NAME / PID_FILE_NAME
PORT_FILE = Path.home() / STATE_DIR_NAME / PORT_FILE_NAME


def state_dir() -> Path:
    """Return the directory where daemon state files live (~/.mentor/)."""
    return Path.home() / STATE_DIR_NAME


def ensure_state_dir() -> None:
    """Create the state directory if it does not exist."""
    state_dir().mkdir(parents=True, exist_ok=True)


def write_state(pid: int, port: int) -> None:
    """Persist the running daemon's PID and port."""
    ensure_state_dir()
    PID_FILE.write_text(str(pid), encoding="utf-8")
    PORT_FILE.write_text(str(port), encoding="utf-8")


def read_pid() -> int | None:
    """Return the stored PID, or None if no valid PID file exists."""
    try:
        return int(PID_FILE.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def read_port() -> int | None:
    """Return the stored port, or None if no valid port file exists."""
    try:
        return int(PORT_FILE.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def pid_alive(pid: int) -> bool:
    """Return True if a process with the given PID exists."""
    if pid <= 0:
        return False
    if os.name == "nt":
        return _pid_alive_windows(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # Exists, but owned by another user.
    return True


def _pid_alive_windows(pid: int) -> bool:
    """Check process liveness on Windows without touching the process."""
    import ctypes

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if handle:
        kernel32.CloseHandle(handle)
        return True
    return False  # ERROR_INVALID_PARAMETER (87) => no such process


def port_open(port: int, host: str = "127.0.0.1") -> bool:
    """Return True if something is listening on the given host/port."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1.0)
        try:
            sock.connect((host, port))
        except OSError:
            return False
    return True


def is_running() -> tuple[int, int] | None:
    """Return ``(pid, port)`` if the daemon appears to be running, else None.

    A daemon counts as running only when all of the following hold: state
    files exist, the stored PID is alive, and the stored port is accepting
    connections. Stale state from a crashed daemon is treated as not running.
    """
    pid = read_pid()
    port = read_port()
    if pid is None or port is None:
        return None
    if not pid_alive(pid) or not port_open(port):
        return None
    return pid, port


def clear_state() -> None:
    """Remove PID/port files (used when the daemon is stopped or stale)."""
    for path in (PID_FILE, PORT_FILE):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
