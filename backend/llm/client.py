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

import json
import os
from pathlib import Path
from typing import Any, Optional

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

GRADING_SYSTEM_PROMPT = (
    "You are Mentor, an AI mentor grading a learner's answer to a concept "
    "question. Judge whether the answer shows real understanding of the "
    "concept. Be fair: accept correct answers even if they are worded "
    "differently from a textbook, but reject answers that are wrong or "
    "miss the point. Respond ONLY with a JSON object of the form "
    '{"correct": true or false, "feedback": "..."}. Keep feedback to '
    "1-2 sentences: if the answer is wrong, name the key idea the learner "
    "missed without giving the full answer away."
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


def generate_reply(
    user_message: str,
    model: str = DEFAULT_MODEL,
    history: Optional[list[dict]] = None,
) -> str:
    """Ask Groq for a reply to ``user_message`` using the Mentor persona.

    ``history`` is an optional list of prior turns (``{"role", "content"}``
    dicts, oldest first) so follow-up questions keep their context.

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
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for entry in history or []:
            role = entry.get("role")
            content = (entry.get("content") or "").strip()
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": user_message})
        completion = client.chat.completions.create(
            model=model,
            messages=messages,
            max_completion_tokens=MAX_COMPLETION_TOKENS,
        )
    except Exception as exc:  # noqa: BLE001 - surface any API/network failure
        return f"(I couldn't reach Groq: {exc})"
    return completion.choices[0].message.content or ""


def grade_answer(
    question: str,
    answer: str,
    concept_name: str,
    concept_category: str = "",
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    """Grade a learner's answer to a concept question via the LLM.

    Returns ``{"correct": bool, "feedback": str}``.  Never raises: any
    failure (missing key, API error, unparseable output) is converted into
    a conservative result — the answer is graded as not-correct with a
    readable explanation, so a broken grader can never inflate progress.
    """
    api_key = resolve_api_key()
    if not api_key:
        return {
            "correct": False,
            "feedback": (
                "(Grading needs a Groq API key — set GROQ_API_KEY or add it "
                "to a .env file, then submit again.)"
            ),
        }

    category_note = f" (category: {concept_category})" if concept_category else ""
    user_prompt = (
        f"Concept: {concept_name}{category_note}\n"
        f"Question: {question}\n\n"
        f"Learner's answer: {answer}\n\n"
        "Grade the answer. Respond ONLY with the JSON object."
    )
    try:
        client = get_client()
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": GRADING_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_completion_tokens=512,
        )
        raw = (completion.choices[0].message.content or "").strip()
        # Tolerate code fences or prose around the JSON object.
        start, end = raw.find("{"), raw.rfind("}")
        if start == -1 or end <= start:
            raise ValueError(f"no JSON object in grader output: {raw[:200]}")
        parsed = json.loads(raw[start : end + 1])
        correct = bool(parsed.get("correct", False))
        feedback = str(parsed.get("feedback", "")).strip()
        return {"correct": correct, "feedback": feedback or ("Correct!" if correct else "Not quite — try again.")}
    except Exception as exc:  # noqa: BLE001 - conservative failure
        return {
            "correct": False,
            "feedback": f"(Grading failed: {exc}. Your answer was not recorded as correct — please submit again.)",
        }
