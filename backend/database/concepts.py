"""Concept storage — persists learned concepts per session.

Storage is a single SQLite database (``~/.mentor/mentor.db``) with three
tables — ``concepts``, ``teachings``, ``assessments`` — mirroring the
previous three JSON stores.  WAL journal mode is enabled so the daemon
can write while the dashboard reads concurrently without
``database is locked`` errors.

Concepts are keyed by *identity*: a stable slug derived from the concept
name, not by which file it happened to appear in.  A concept carries a
``content_hash`` of the underlying code it was detected from, so the
detect node can reuse a previously stored explanation/diagram without
recomputing when the concept resurfaces — in the same file or a
different one — and only recompute when the underlying code actually
changed.
"""

from __future__ import annotations

import functools
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

from backend.database.concept_slug import concept_slug, normalize_concept_name


def _resolve_db_path() -> Path:
    """Resolve the store location — fail closed under test runners.

    When the process looks like a test run (unittest/pytest in argv,
    or pytest's env marker), the store resolves into a per-process temp
    directory instead of the user's real ``~/.mentor``.  This is the
    hard structural guarantee that a test can never pollute real data:
    it does not depend on any fixture remembering to patch DB_PATH —
    an unisolated test simply lands in temp space, where a wrong
    assertion is the worst outcome.

    argv[0] is included in the check because ``python -m unittest``
    puts the runner's path there, not in the arguments.
    """
    argv = " ".join(sys.argv).lower()
    argv0 = os.path.basename(sys.argv[0] or "").lower()
    under_test_runner = (
        "unittest" in argv
        or "pytest" in argv
        or "test" in argv0  # direct execution: python tests/test_x.py
        or "PYTEST_CURRENT_TEST" in os.environ
    )
    if under_test_runner:
        return (
            Path(tempfile.gettempdir()) / "mentor-tests"
            / f"mentor-{os.getpid()}.db"
        )
    return Path.home() / ".mentor" / "mentor.db"


DB_PATH = _resolve_db_path()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS concepts (
    slug         TEXT NOT NULL,
    session      TEXT NOT NULL,
    name         TEXT NOT NULL,
    category     TEXT NOT NULL DEFAULT '',
    subcategory  TEXT NOT NULL DEFAULT '',
    description  TEXT NOT NULL DEFAULT '',
    decision     TEXT NOT NULL DEFAULT '',
    diagram      TEXT NOT NULL DEFAULT '',
    source_file  TEXT NOT NULL DEFAULT '',
    content_hash TEXT NOT NULL DEFAULT '',
    line_start   INTEGER NOT NULL DEFAULT 0,
    line_end     INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (slug, session)
);

CREATE TABLE IF NOT EXISTS teachings (
    slug         TEXT NOT NULL,
    session      TEXT NOT NULL,
    concept_name TEXT NOT NULL,
    category     TEXT NOT NULL DEFAULT '',
    explanation  TEXT NOT NULL DEFAULT '',
    decision     TEXT NOT NULL DEFAULT '',
    diagram      TEXT NOT NULL DEFAULT '',
    source_file  TEXT NOT NULL DEFAULT '',
    content_hash TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (slug, session)
);

CREATE TABLE IF NOT EXISTS assessments (
    id           TEXT NOT NULL,
    session      TEXT NOT NULL,
    payload      TEXT NOT NULL,
    answered     INTEGER NOT NULL DEFAULT 0,
    correct      INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (id, session)
);
"""



_schema_lock = threading.Lock()
_schema_ready = False

# Serializes writers *within this process*.  The daemon's thread pool
# would otherwise stampede SQLite's lock-retry logic from many threads
# at once; an in-memory queue is cheaper and deterministic.  Writers
# from OTHER processes queue via busy_timeout + BEGIN IMMEDIATE below.
_write_lock = threading.Lock()


def _retry_on_busy(fn: Callable) -> Callable:
    """Retry a store operation on transient SQLITE_BUSY/LOCKED errors.

    Third layer of the concurrency story (after the in-process write
    lock and BEGIN IMMEDIATE + busy_timeout): WAL checkpoints and
    cross-process lockers can still briefly block an operation past
    what the busy handler absorbs.  "database is locked" must never
    reach a user of this store; a bounded exponential backoff turns
    the residual window into a wait.  All store operations are safe
    to re-run — the transaction rolls back atomically on failure.
    """

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        delay = 0.05
        for attempt in range(4):
            try:
                return fn(*args, **kwargs)
            except sqlite3.OperationalError as exc:
                msg = str(exc).lower()
                transient = "locked" in msg or "busy" in msg
                if not transient or attempt == 3:
                    raise
                time.sleep(delay)
                delay *= 2
        return None  # unreachable; keeps type-checkers content

    return wrapper


def ensure_schema() -> None:
    """Create the tables if they do not exist yet (idempotent, thread-safe)."""
    global _schema_ready
    if _schema_ready:
        return
    with _schema_lock:
        if _schema_ready:
            return
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(DB_PATH))
        # busy_timeout BEFORE any DDL: table creation takes the write
        # lock, and the default 0 would make a concurrent first-touch
        # fail instantly instead of waiting.
        conn.execute("PRAGMA busy_timeout=5000")
        try:
            conn.executescript(_SCHEMA)
            # Columns added after first release: a database created by an
            # older build lacks them, and CREATE TABLE IF NOT EXISTS does
            # not repair an existing table.  Idempotent: ALTER fails with
            # "duplicate column" when the column is already there.
            for table in ("concepts", "teachings"):
                try:
                    conn.execute(
                        f"ALTER TABLE {table} ADD COLUMN decision "
                        "TEXT NOT NULL DEFAULT ''"
                    )
                except sqlite3.OperationalError as exc:
                    if "duplicate column" not in str(exc).lower():
                        raise
            conn.commit()
        finally:
            conn.close()
        _schema_ready = True


@contextmanager
def _connect(write: bool = True) -> Iterator[sqlite3.Connection]:
    """Yield a per-operation connection, always closed afterwards.

    sqlite3 connections commit on context exit but do NOT close — on
    Windows an open handle keeps the database file locked, so every
    operation must close explicitly.  One connection per operation
    (opened and closed on the same thread) avoids SQLite's
    ``check_same_thread`` restriction under the daemon's thread pool.

    ``PRAGMA synchronous=NORMAL`` is the recommended pairing with WAL —
    durable across app crashes, no per-commit fsync stall.

    Two concurrency mechanisms, one per contention domain:

    - ``write=False`` opens an autocommit READER.  In WAL mode readers
      never block writers and vice versa, so a read must not queue on
      the write lock (or it would just add write pressure).
    - ``write=True`` (default) acquires the in-process ``_write_lock`",
      then takes the database write lock via ``BEGIN IMMEDIATE`` — not
      the default DEFERRED, which fails with a non-retryable
      ``database is locked`` (SQLITE_BUSY_SNAPSHOT) when another
      process commits between this transaction's read and its write;
      busy_timeout cannot help a deferred snapshot.  IMMEDIATE makes
      cross-process writers queue via busy_timeout instead.
    """
    ensure_schema()
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    # isolation_level=None: Python stops managing implicit DEFERRED
    # transactions, so the explicit BEGIN IMMEDIATE below governs.
    conn = sqlite3.connect(str(DB_PATH), isolation_level=None)
    conn.row_factory = sqlite3.Row
    # busy_timeout FIRST: it must be in effect before anything that can
    # touch a lock — including the journal_mode pragma below, whose
    # WAL-index lock acquisition fails instantly (default timeout 0)
    # when another connection is mid-commit.
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    if write:
        _write_lock.acquire()
    try:
        if write:
            conn.execute("BEGIN IMMEDIATE")
        yield conn
        if write:
            conn.commit()
    except BaseException:
        if write:
            conn.rollback()
        raise
    finally:
        conn.close()
        if write:
            _write_lock.release()


def content_hash(code: str) -> str:
    """Stable short hash of the code a concept was detected in."""
    return hashlib.sha256(code.encode("utf-8", "replace")).hexdigest()[:16]


def _row_to_concept(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "slug": row["slug"],
        "name": row["name"],
        "category": row["category"],
        "subcategory": row["subcategory"],
        "description": row["description"],
        "decision": row["decision"],
        "diagram": row["diagram"],
        "source_file": row["source_file"],
        "content_hash": row["content_hash"],
        "line_range": [row["line_start"], row["line_end"]],
    }


# ---------------------------------------------------------------------------
# Concepts
# ---------------------------------------------------------------------------

@_retry_on_busy
def load_concepts(session: str = "default") -> list[dict[str, Any]]:
    """Load all stored concepts for *session* in insertion order."""
    with _connect(write=False) as conn:
        rows = conn.execute(
            "SELECT * FROM concepts WHERE session = ? ORDER BY rowid",
            (session,),
        ).fetchall()
    return [_row_to_concept(r) for r in rows]


@_retry_on_busy
def save_concept(
    session: str,
    name: str,
    category: str,
    description: str,
    source_file: str = "",
    diagram: str = "",
    subcategory: str = "",
    code_hash: str = "",
    decision: str = "",
) -> dict[str, Any]:
    """Insert or refresh a concept, keyed by slug identity.

    Returns the saved concept dict.  A re-detection of the same concept
    name in a different file *moves* the concept to the new source
    (identity is the name, not the file) and refreshes its metadata;
    the teaching entry keeps its original explanation (see
    :func:`save_teaching`), so the dashboard stays consistent.
    """
    slug = concept_slug(name)
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO concepts
                (slug, session, name, category, subcategory, description,
                 decision, diagram, source_file, content_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(slug, session) DO UPDATE SET
                name = excluded.name,
                category = excluded.category,
                subcategory = excluded.subcategory,
                description = excluded.description,
                decision = CASE
                    WHEN excluded.decision != '' THEN excluded.decision
                    ELSE concepts.decision END,
                diagram = CASE
                    WHEN excluded.diagram != '' THEN excluded.diagram
                    ELSE concepts.diagram END,
                source_file = excluded.source_file,
                content_hash = excluded.content_hash
            """,
            (slug, session, name, category, subcategory, description,
             decision, diagram, source_file, code_hash),
        )
    return {
        "slug": slug,
        "name": name,
        "category": category,
        "subcategory": subcategory,
        "description": description,
        "decision": decision,
        "diagram": diagram,
        "source_file": source_file,
        "content_hash": code_hash,
        "line_range": [0, 0],
    }


@_retry_on_busy
def save_concepts_bulk(
    session: str,
    concepts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge concept dicts into the session store, keyed by identity.

    Accepts both rich dicts (with ``subcategory``/``diagram``/``code_hash``)
    and the plain dicts stored by the legacy JSON format.  Returns the
    full list of stored concepts after the merge.
    """
    existing_by_slug = {c["slug"]: c for c in load_concepts(session)}

    for c in concepts:
        name = c.get("name", "")
        if not name:
            continue
        existing = existing_by_slug.get(concept_slug(name))
        code_hash = c.get("code_hash") or c.get("content_hash") or ""
        if existing is not None:
            # Same identity, new sighting: refresh provenance, keep the
            # richer stored content unless the new one carries more.
            existing["source_file"] = c.get("source_file", "") or existing["source_file"]
            existing["line_range"] = c.get("line_range") or existing.get("line_range", [0, 0])
            if code_hash:
                existing["content_hash"] = code_hash
            if c.get("subcategory"):
                existing["subcategory"] = c["subcategory"]
            if c.get("description"):
                existing["description"] = c["description"]
            if c.get("category"):
                existing["category"] = c["category"]
            if c.get("decision"):
                existing["decision"] = c["decision"]
            if c.get("diagram"):
                existing["diagram"] = c["diagram"]
        else:
            concept = {
                "slug": concept_slug(name),
                "name": name,
                "category": c.get("category", ""),
                "subcategory": c.get("subcategory", ""),
                "description": c.get("description", ""),
                "decision": c.get("decision", ""),
                "diagram": c.get("diagram", ""),
                "source_file": c.get("source_file", ""),
                "content_hash": code_hash,
                "line_range": c.get("line_range", [0, 0]),
            }
            existing_by_slug[concept["slug"]] = concept

    concepts_list = list(existing_by_slug.values())
    with _connect() as conn:
        for c in concepts_list:
            conn.execute(
                """
                INSERT INTO concepts
                    (slug, session, name, category, subcategory, description,
                     decision, diagram, source_file, content_hash,
                     line_start, line_end)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(slug, session) DO UPDATE SET
                    name = excluded.name,
                    category = excluded.category,
                    subcategory = excluded.subcategory,
                    description = excluded.description,
                    decision = CASE
                        WHEN excluded.decision != '' THEN excluded.decision
                        ELSE concepts.decision END,
                    diagram = CASE
                        WHEN excluded.diagram != '' THEN excluded.diagram
                        ELSE concepts.diagram END,
                    source_file = excluded.source_file,
                    content_hash = excluded.content_hash,
                    line_start = excluded.line_start,
                    line_end = excluded.line_end
                """,
                (c["slug"], session, c["name"], c["category"],
                 c.get("subcategory", ""), c.get("description", ""),
                 c.get("decision", ""), c.get("diagram", ""),
                 c.get("source_file", ""),
                 c.get("content_hash", ""),
                 (c.get("line_range") or [0, 0])[0],
                 (c.get("line_range") or [0, 0])[1]),
            )
    return concepts_list


@_retry_on_busy
def get_cached_teaching(
    session: str, slug: str, code_hash: str
) -> dict[str, Any] | None:
    """Return the cached teaching for a concept whose code is unchanged.

    Cache hit requires BOTH the same concept identity (slug) and the
    same ``content_hash`` — the underlying code for that concept must
    be unchanged, otherwise the explanation may be stale.
    """
    with _connect(write=False) as conn:
        row = conn.execute(
            """
            SELECT t.* FROM teachings t
            JOIN concepts c ON c.slug = t.slug AND c.session = t.session
            WHERE t.slug = ? AND t.session = ? AND t.content_hash != ''
              AND t.content_hash = ? AND c.content_hash = ?
            """,
            (slug, session, code_hash, code_hash),
        ).fetchone()
    if row is None:
        return None
    return {
        "slug": row["slug"],
        "concept_name": row["concept_name"],
        "concept_category": row["category"],
        "explanation": row["explanation"],
        "decision": row["decision"],
        "diagram": row["diagram"],
        "source_file": row["source_file"],
        "content_hash": row["content_hash"],
        "cached": True,
    }


@_retry_on_busy
def get_cached_diagram(
    session: str, slug: str, code_hash: str
) -> str:
    """Return the stored diagram for a concept whose code is unchanged."""
    with _connect(write=False) as conn:
        row = conn.execute(
            """
            SELECT c.diagram FROM concepts c
            WHERE c.slug = ? AND c.session = ? AND c.content_hash = ?
              AND c.diagram != ''
            """,
            (slug, session, code_hash),
        ).fetchone()
    return row["diagram"] if row else ""


@_retry_on_busy
def file_scan_cached(
    session: str, source_file: str, code_hash: str
) -> bool:
    """True when this exact file content was already LLM-scanned.

    The generation-time identity cache: keys on (session, path,
    content_hash).  True means a stored concept was detected from
    *this same content* of *this same file* — its explanation lives in
    the teachings table and its detection cost is already sunk — so
    the detect node skips the whole LLM generation call for the file.

    Requires a non-empty code_hash: hash-less callers never consult
    (nor can they ever pollute) the store.
    """
    if not code_hash:
        return False
    with _connect(write=False) as conn:
        row = conn.execute(
            """
            SELECT 1 FROM concepts c
            JOIN teachings t ON t.slug = c.slug AND t.session = c.session
            WHERE c.session = ? AND c.source_file = ?
              AND c.content_hash = ?
            LIMIT 1
            """,
            (session, source_file, code_hash),
        ).fetchone()
    return row is not None


# ---------------------------------------------------------------------------
# Assessment storage
# ---------------------------------------------------------------------------

@_retry_on_busy
def get_pending_assessments(session: str = "default") -> list[dict[str, Any]]:
    """Return the current (first unanswered) assessment for *session*.

    Only one question is surfaced at a time — the rest stay queued in
    storage and are promoted as earlier ones get answered.
    """
    with _connect(write=False) as conn:
        rows = conn.execute(
            "SELECT payload FROM assessments WHERE session = ? "
            "ORDER BY created_at, rowid",
            (session,),
        ).fetchall()
    for r in rows:
        a = json.loads(r["payload"])
        if not a.get("answered", False):
            return [a]
    return []


@_retry_on_busy
def get_assessment_counts(session: str = "default") -> dict[str, int]:
    """Return counts for the assessment queue.

    - ``total``: all assessments ever generated
    - ``answered``: how many the user has answered
    - ``pending``: unanswered assessments (the current question + queue)
    - ``queued``: unanswered assessments waiting behind the current one
    """
    with _connect(write=False) as conn:
        rows = conn.execute(
            "SELECT payload FROM assessments WHERE session = ?",
            (session,),
        ).fetchall()
    assessments = [json.loads(r["payload"]) for r in rows]
    answered = [a for a in assessments if a.get("answered", False)]
    pending = [a for a in assessments if not a.get("answered", False)]
    return {
        "total": len(assessments),
        "answered": len(answered),
        "pending": len(pending),
        "queued": max(0, len(pending) - 1),
    }


@_retry_on_busy
def get_all_assessments(session: str = "default") -> list[dict[str, Any]]:
    """Load all assessments (answered and unanswered) for *session*."""
    with _connect(write=False) as conn:
        rows = conn.execute(
            "SELECT payload FROM assessments WHERE session = ? "
            "ORDER BY created_at, rowid",
            (session,),
        ).fetchall()
    return [json.loads(r["payload"]) for r in rows]


@_retry_on_busy
def save_assessment(session: str, assessment: dict[str, Any]) -> None:
    """Append an assessment to the session's store. Deduplicates by id."""
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO assessments (id, session, payload, answered, correct)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id, session) DO NOTHING
            """,
            (
                assessment["id"],
                session,
                json.dumps(assessment, ensure_ascii=False),
                1 if assessment.get("answered", False) else 0,
                1 if assessment.get("correct", False) else 0,
            ),
        )


@_retry_on_busy
def submit_assessment_answer(
    session: str,
    assessment_id: str,
    answer: str,
    correct: bool = False,
    feedback: str = "",
) -> dict[str, Any] | None:
    """Record an attempt at an assessment. Returns the updated assessment or None.

    A correct answer marks the assessment as answered; an incorrect one is
    stored as ``feedback``/``last_answer`` on the still-open question so
    the learner can retry.  Only correct answers count toward progress.
    """
    with _connect() as conn:
        row = conn.execute(
            "SELECT payload FROM assessments WHERE id = ? AND session = ?",
            (assessment_id, session),
        ).fetchone()
        if row is None:
            return None
        a = json.loads(row["payload"])
        a["attempts"] = int(a.get("attempts", 0)) + 1
        a["last_answer"] = answer
        a["feedback"] = feedback
        if correct:
            a["answered"] = True
            a["correct"] = True
            a["answer"] = answer
        conn.execute(
            "UPDATE assessments SET payload = ?, answered = ?, correct = ? "
            "WHERE id = ? AND session = ?",
            (
                json.dumps(a, ensure_ascii=False),
                1 if a.get("answered", False) else 0,
                1 if a.get("correct", False) else 0,
                assessment_id,
                session,
            ),
        )
    return a


@_retry_on_busy
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


@_retry_on_busy
def clear_assessments(session: str = "default") -> None:
    """Delete all stored assessments for *session*."""
    with _connect() as conn:
        conn.execute("DELETE FROM assessments WHERE session = ?", (session,))


# ---------------------------------------------------------------------------
# Teaching storage (for dashboard)
# ---------------------------------------------------------------------------

@_retry_on_busy
def save_teaching(session: str, teaching: dict[str, Any]) -> None:
    """Append a teaching entry to the session's store.

    Pure validation gate: the entry's ``diagram`` (Mermaid) is checked
    before the write and stripped to "" when invalid, so the dashboard
    renders the prose explanation instead of a syntax error.

    No repair happens here — a safety net must be cheap and
    deterministic, and this layer has none of the context (concept
    name, description, source code) a good repair prompt needs.  The
    single LLM repair attempt lives in
    :func:`backend.agents.concept_detector.detect_concepts_with_llm`,
    whose backfill runs with that context; this gate is defense in
    depth against any future caller that bypasses it.

    Entries are keyed by concept identity (slug, session): saving a
    teaching for an existing concept is a no-op unless the stored
    ``content_hash`` differs from the incoming one (i.e. the underlying
    code changed) — keeping a concept's explanation stable across
    re-detections.
    """
    from backend.agents.concept_detector import is_valid_mermaid

    diagram = teaching.get("diagram") or ""
    if diagram and not is_valid_mermaid(diagram):
        teaching = {**teaching, "diagram": ""}

    slug = teaching.get("slug") or concept_slug(teaching.get("concept_name", ""))
    code_hash = teaching.get("content_hash", "")

    with _connect() as conn:
        existing = conn.execute(
            "SELECT content_hash FROM teachings WHERE slug = ? AND session = ?",
            (slug, session),
        ).fetchone()
        if existing is not None and existing["content_hash"] == code_hash:
            return  # cached: same concept, same code — keep stored entry

        conn.execute(
            """
            INSERT INTO teachings
                (slug, session, concept_name, category, explanation,
                 decision, diagram, source_file, content_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(slug, session) DO UPDATE SET
                concept_name = excluded.concept_name,
                category = excluded.category,
                explanation = excluded.explanation,
                decision = excluded.decision,
                diagram = excluded.diagram,
                source_file = excluded.source_file,
                content_hash = excluded.content_hash,
                created_at = datetime('now')
            """,
            (
                slug,
                session,
                teaching.get("concept_name", ""),
                teaching.get("concept_category", ""),
                teaching.get("explanation", ""),
                teaching.get("decision", ""),
                teaching.get("diagram", ""),
                teaching.get("source_file", ""),
                code_hash,
            ),
        )


@_retry_on_busy
def get_teachings(session: str = "default") -> list[dict[str, Any]]:
    """Load all teaching entries for *session* in insertion order."""
    with _connect(write=False) as conn:
        rows = conn.execute(
            "SELECT * FROM teachings WHERE session = ? ORDER BY rowid",
            (session,),
        ).fetchall()
    return [
        {
            "slug": r["slug"],
            "concept_name": r["concept_name"],
            "concept_category": r["category"],
            "explanation": r["explanation"],
            "decision": r["decision"],
            "diagram": r["diagram"],
            "source_file": r["source_file"],
            "content_hash": r["content_hash"],
        }
        for r in rows
    ]


@_retry_on_busy
def clear_teachings(session: str = "default") -> None:
    """Delete all stored teachings for *session*."""
    with _connect() as conn:
        conn.execute("DELETE FROM teachings WHERE session = ?", (session,))


@_retry_on_busy
def clear_concepts(session: str = "default") -> None:
    """Delete all stored concepts for *session*."""
    with _connect() as conn:
        conn.execute("DELETE FROM concepts WHERE session = ?", (session,))


# ---------------------------------------------------------------------------
# Progress
# ---------------------------------------------------------------------------

@_retry_on_busy
def get_progress(session: str = "default") -> dict[str, Any]:
    """Return a summary of the user's learning progress.

    Progress is mastery-based: a concept only counts once its assessment
    question has been answered *correctly*.  Concepts that were merely
    detected still appear in ``concepts`` (and in ``detected``) but do not
    count toward ``total_concepts`` or ``categories``.
    """
    concepts = load_concepts(session)
    assessments = get_all_assessments(session)

    mastered_names = {
        a.get("concept_name", "")
        for a in assessments
        if a.get("answered", False) and a.get("correct", False)
    }

    categories: dict[str, int] = {}
    mastered: list[dict[str, Any]] = []
    for c in concepts:
        if c.get("name") in mastered_names:
            mastered.append(c)
            cat = c.get("category", "General")
            categories[cat] = categories.get(cat, 0) + 1

    return {
        "session": session,
        "total_concepts": len(mastered),
        "categories": categories,
        "concepts": concepts,
        "mastered": len(mastered),
        "detected": len(concepts),
    }
