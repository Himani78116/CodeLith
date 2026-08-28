from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from . import state

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVER_MODULE = "backend.daemon.server"
HOST = "127.0.0.1"
DEFAULT_PORT = 8765  # Match the dashboard's hardcoded port
READY_TIMEOUT_SECONDS = 15.0


def _find_venv_python() -> str:
    """Find the project's venv Python, or fall back to sys.executable."""
    # Check for .venv in project root
    venv_python = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        return str(venv_python)
    # Unix
    venv_python = REPO_ROOT / ".venv" / "bin" / "python"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def _find_free_port(host: str = HOST, preferred: int = DEFAULT_PORT) -> int:
    """Try *preferred* port first; fall back to a random free port."""
    import socket

    # Try preferred port first
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, preferred))
            return preferred
        except OSError:
            pass  # Port in use, fall back

    # Fall back to random port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return sock.getsockname()[1]


def _wait_until_ready(port: int, timeout: float = READY_TIMEOUT_SECONDS) -> bool:
    """Poll the daemon's /health endpoint until it responds or we time out."""
    url = f"http://{HOST}:{port}/health"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as resp:
                if resp.status == 200:
                    return True
        except OSError:
            pass
        time.sleep(0.2)
    return False


def _daemon_command(port: int) -> tuple[list[str], dict[str, str]]:
    """Return ``(argv, env)`` for the detached daemon process.

    Detects the project's venv Python so the daemon always has access to
    installed packages, regardless of which Python was used to invoke the
    launcher.
    """
    env = dict(os.environ)
    python = _find_venv_python()
    argv = [python, "-m", SERVER_MODULE, "--host", HOST, "--port", str(port)]
    return argv, env


def _start_detached(port: int) -> subprocess.Popen:
    """Spawn the daemon server in a detached process with its own session."""
    state.ensure_state_dir()
    log = (state.state_dir() / "daemon.log").open("a", encoding="utf-8")
    argv, env = _daemon_command(port)
    kwargs: dict = {
        "cwd": str(REPO_ROOT),
        "env": env,
        "stdin": subprocess.DEVNULL,
        "stdout": log,
        "stderr": subprocess.STDOUT,
    }
    if sys.platform == "win32":
        # Hide the console window without using DETACHED_PROCESS
        # (DETACHED_PROCESS can break subprocess environment on Windows).
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0  # SW_HIDE
        kwargs["startupinfo"] = si
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(argv, **kwargs)


def start() -> tuple[int, int, bool]:
    """Start the daemon if it is not already running.

    Returns ``(pid, port, started_now)``.
    """
    running = state.is_running()
    if running:
        pid, port = running
        print(f"Daemon already running (pid {pid}, port {port}).")
        return pid, port, False

    # Clear stale state left behind by a crashed or stopped daemon.
    state.clear_state()

    port = _find_free_port()
    proc = _start_detached(port)
    state.write_state(proc.pid, port)
    if not _wait_until_ready(port):
        _print_log_tail()
        raise SystemExit(
            f"Daemon failed to become ready within {READY_TIMEOUT_SECONDS:.0f}s; "
            f"see {state.state_dir() / 'daemon.log'}"
        )
    print(f"Daemon started (pid {proc.pid}, port {port}).")
    return proc.pid, port, True


def status() -> None:
    """Print whether the daemon is running and its PID/port."""
    running = state.is_running()
    if running:
        pid, port = running
        print(f"Daemon is running (pid {pid}, port {port}).")
        return
    pid = state.read_pid()
    port = state.read_port()
    if pid is not None or port is not None:
        print(f"Daemon is not running (stale state: pid={pid}, port={port}).")
    else:
        print("Daemon is not running.")


def _terminate(pid: int) -> None:
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/F"],
            check=False,
            capture_output=True,
        )
    else:
        import os
        import signal

        os.kill(pid, signal.SIGTERM)


def stop() -> bool:
    """Stop the running daemon and clear its state. Returns True if one was running."""
    pid = state.read_pid()
    if pid is None:
        print("No daemon state found; nothing to stop.")
        return False
    if state.pid_alive(pid):
        _terminate(pid)
        print(f"Stopped daemon (pid {pid}).")
    else:
        print(f"State refers to dead pid {pid}; cleaning up.")
    state.clear_state()
    return True


def _print_log_tail() -> None:
    log = state.state_dir() / "daemon.log"
    try:
        tail = "\n".join(log.read_text(encoding="utf-8").splitlines()[-20:])
    except OSError:
        return
    if tail:
        print("--- daemon.log tail ---")
        print(tail)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="codelith-daemon",
        description="Manage the CodeLith local daemon.",
    )
    parser.add_argument("command", choices=["start", "status", "stop"])
    args = parser.parse_args(argv)

    if args.command == "start":
        start()
    elif args.command == "status":
        status()
    elif args.command == "stop":
        stop()


if __name__ == "__main__":
    main()
