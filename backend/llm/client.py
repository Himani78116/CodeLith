"""Groq-backed chat client for the CodeLith daemon.

The API key is resolved from, in order:

1. the ``GROQ_API_KEY`` environment variable,
2. a ``.env`` file in the repository root,
3. a ``.env`` file in the daemon state directory (``~/.mentor/``).

Files are re-read on every request, so adding the key to a ``.env`` file
takes effect without restarting the daemon. Usage::

    from backend.llm.client import generate_reply

    reply = generate_reply("What is a closure?")
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from openai import OpenAI

GROQ_API_KEY_ENV = "GROQ_API_KEY"
DEFAULT_MODEL = "openai/gpt-oss-120b"
MAX_COMPLETION_TOKENS = 4096
GROQ_BASE_URL = "https://api.groq.com/openai/v1"

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILES = (
    REPO_ROOT / ".env",
    Path.home() / ".mentor" / ".env",
)

SYSTEM_PROMPT = (
    "You are Mentor, an AI mentor that blends coding assistance with "
    "adaptive teaching. The user is learning to code. Teach at their level: "
    "explain concepts clearly, use concrete examples, and guide them toward "
    "solutions instead of just giving the answer. Keep answers focused and "
    "conversational, and ask a question now and then to check understanding."
)


def _load_dotenv(path: Path) -> None:
    """Load ``KEY=VALUE`` pairs from ``path`` without overriding existing vars."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def resolve_api_key() -> Optional[str]:
    """Return the Groq API key, or None if it is not configured anywhere."""
    if os.environ.get(GROQ_API_KEY_ENV):
        return os.environ[GROQ_API_KEY_ENV].strip()
    for path in ENV_FILES:
        _load_dotenv(path)
        key = os.environ.get(GROQ_API_KEY_ENV)
        if key:
            return key.strip()
    return None


def get_client() -> OpenAI:
    """Return an OpenAI-compatible client pointed at Groq."""
    api_key = resolve_api_key()
    if not api_key:
        raise ValueError(
            "No Groq API key found. Set GROQ_API_KEY "
            "environment variable, or add it to a .env file."
        )
    return OpenAI(
        base_url=GROQ_BASE_URL,
        api_key=api_key,
    )


def generate_reply(user_message: str, model: str = DEFAULT_MODEL) -> str:
    """Ask Groq for a reply to ``user_message`` using the Mentor persona.

    Never raises: a missing API key and API/network failures are converted
    into a readable message so the CLI keeps working without a key.
    """
    api_key = resolve_api_key()
    if not api_key:
        return (
            "I need a Groq API key to think. Set the GROQ_API_KEY "
            "environment variable, or add it to a .env file in the project "
            "root (see the README), then try again."
        )
    try:
        client = get_client()
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            max_completion_tokens=MAX_COMPLETION_TOKENS,
        )
    except Exception as exc:  # noqa: BLE001 - surface any API/network failure
        return f"(I couldn't reach Groq: {exc})"
    return completion.choices[0].message.content or ""
