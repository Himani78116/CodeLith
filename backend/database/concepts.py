"""Concept storage — persists learned concepts per session.

Concepts are stored as JSON in ``~/.mentor/concepts/<session>.json`` so
the dashboard can retrieve them and the user can review past concepts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CONCEPTS_DIR = Path.home() / ".mentor" / "concepts"


def _concepts_file(session: str) -> Path:
    """Return the path to the concepts file for *session*."""
    CONCEPTS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = session.replace("/", "_").replace("\\", "_")
    return CONCEPTS_DIR / f"{safe_name}.json"


def load_concepts(session: str = "default") -> list[dict[str, Any]]:
    """Load all stored concepts for *session*."""
    path = _concepts_file(session)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def save_concept(
    session: str,
    name: str,
    category: str,
    description: str,
    source_file: str = "",
) -> dict[str, Any]:
    """Append a new concept to the session's store.

    Returns the saved concept dict.  Deduplicates by name — if the
    concept already exists, it is NOT added again.
    """
    concepts = load_concepts(session)

    # Deduplicate
    if any(c["name"] == name for c in concepts):
        return next(c for c in concepts if c["name"] == name)

    concept = {
        "name": name,
        "category": category,
        "description": description,
        "source_file": source_file,
    }
    concepts.append(concept)

    path = _concepts_file(session)
    path.write_text(
        json.dumps(concepts, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return concept


def save_concepts_bulk(
    session: str,
    concepts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge a list of concept dicts into the session store, deduplicating.

    Returns the full list of stored concepts after the merge.
    """
    existing = load_concepts(session)
    existing_names = {c["name"] for c in existing}

    for c in concepts:
        if c["name"] not in existing_names:
            existing.append(c)
            existing_names.add(c["name"])

    path = _concepts_file(session)
    path.write_text(
        json.dumps(existing, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return existing


def get_progress(session: str = "default") -> dict[str, Any]:
    """Return a summary of the user's learning progress.

    Includes total concepts learned, categories covered, and the
    concept list itself.
    """
    concepts = load_concepts(session)
    categories: dict[str, int] = {}
    for c in concepts:
        cat = c.get("category", "General")
        categories[cat] = categories.get(cat, 0) + 1

    return {
        "session": session,
        "total_concepts": len(concepts),
        "categories": categories,
        "concepts": concepts,
    }


def clear_concepts(session: str = "default") -> None:
    """Delete all stored concepts for *session*."""
    path = _concepts_file(session)
    if path.exists():
        path.unlink()


# ---------------------------------------------------------------------------
# Assessment storage
# ---------------------------------------------------------------------------

ASSESSMENTS_DIR = Path.home() / ".mentor" / "assessments"


def _assessments_file(session: str) -> Path:
    """Return the path to the assessments file for *session*."""
    ASSESSMENTS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = session.replace("/", "_").replace("\\", "_")
    return ASSESSMENTS_DIR / f"{safe_name}.json"


def get_pending_assessments(session: str = "default") -> list[dict[str, Any]]:
    """Load all pending (unanswered) assessments for *session*."""
    path = _assessments_file(session)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            return []
        return [a for a in data if not a.get("answered", False)]
    except (json.JSONDecodeError, OSError):
        return []


def get_all_assessments(session: str = "default") -> list[dict[str, Any]]:
    """Load all assessments (answered and unanswered) for *session*."""
    path = _assessments_file(session)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def save_assessment(session: str, assessment: dict[str, Any]) -> None:
    """Append an assessment to the session's store. Deduplicates by id."""
    assessments = get_all_assessments(session)
    existing_ids = {a["id"] for a in assessments}
    if assessment["id"] not in existing_ids:
        assessments.append(assessment)
        path = _assessments_file(session)
        path.write_text(
            json.dumps(assessments, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def submit_assessment_answer(
    session: str,
    assessment_id: str,
    answer: str,
    correct: bool = False,
) -> dict[str, Any] | None:
    """Record the user's answer to an assessment. Returns the updated assessment or None."""
    assessments = get_all_assessments(session)
    for a in assessments:
        if a["id"] == assessment_id:
            a["answered"] = True
            a["answer"] = answer
            a["correct"] = correct
            path = _assessments_file(session)
            path.write_text(
                json.dumps(assessments, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            return a
    return None


def get_assessment_progress(session: str = "default") -> dict[str, Any]:
    """Return a summary of assessment performance."""
    assessments = get_all_assessments(session)
    answered = [a for a in assessments if a.get("answered", False)]
    correct = [a for a in answered if a.get("correct", False)]

    return {
        "session": session,
        "total": len(assessments),
        "answered": len(answered),
        "correct": len(correct),
        "accuracy": round(len(correct) / len(answered) * 100, 1) if answered else 0,
        "assessments": assessments,
    }


# ---------------------------------------------------------------------------
# Teaching storage (for dashboard)
# ---------------------------------------------------------------------------

TEACHINGS_DIR = Path.home() / ".mentor" / "teachings"


def _teachings_file(session: str) -> Path:
    """Return the path to the teachings file for *session*."""
    TEACHINGS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = session.replace("/", "_").replace("\\", "_")
    return TEACHINGS_DIR / f"{safe_name}.json"


def save_teaching(session: str, teaching: dict[str, Any]) -> None:
    """Append a teaching entry to the session's store."""
    path = _teachings_file(session)
    teachings: list[dict[str, Any]] = []
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                teachings = data
        except (json.JSONDecodeError, OSError):
            pass

    teachings.append(teaching)
    path.write_text(
        json.dumps(teachings, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def get_teachings(session: str = "default") -> list[dict[str, Any]]:
    """Load all teaching entries for *session*."""
    path = _teachings_file(session)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []
