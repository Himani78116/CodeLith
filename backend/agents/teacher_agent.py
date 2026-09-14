"""Teacher Agent — saves teaching content and answers user questions.

Concept detection no longer happens here: the shared ``detect_concepts``
node (see :mod:`backend.agents.concept_detector`) runs once per turn and
writes ``state["concepts_detected"]``.  This node reads that shared result
and turns the new concepts into teaching entries on the dashboard.

When the user asks a question in the terminal, the teacher agent answers
it there directly instead.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from backend.llm.client import DEFAULT_MODEL, resolve_api_key, get_client

# Shims for backwards compatibility — the detection engine lives in
# backend.agents.concept_detector now.  These names were importable from
# here before the refactor; keep the re-exports until all call sites
# have moved over.
from backend.agents.concept_detector import (  # noqa: F401
    CONCEPT_PATTERNS,
    DetectedConcept,
    detect_concepts_from_file,
    detect_concepts_from_tool_calls,
    detect_concepts_with_llm,
)


def teacher_agent_node(state: dict[str, Any]) -> dict[str, Any]:
    """LangGraph node: teach the concepts the shared detect_concepts node found.

    Expects ``state["concepts_detected"]`` — written by the detect_concepts
    node each turn as a list of dicts with ``name``, ``category``,
    ``description``, and ``diagram`` keys.

    Expects ``state["concepts"]`` for already-known concepts so we don't
    re-teach them.

    Saves teaching content to the dashboard (via database) rather than
    printing it in the terminal.  Only a brief notification is shown
    in the terminal; the full teaching is available on the dashboard.

    When the user asks a question in the terminal, the teacher agent
    answers there directly.
    """
    from backend.database.concepts import save_teaching

    messages: list[BaseMessage] = state.get("messages", [])
    concepts: list[dict[str, Any]] = state.get("concepts", [])
    session: str = state.get("session", "default")

    # Check if this is a user question — if so, answer it in the terminal
    last_user_msg = None
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            last_user_msg = msg
            break

    if last_user_msg and _is_user_question(last_user_msg.content):
        # User asked a question — answer it directly in the terminal
        answer = _answer_user_question(last_user_msg.content, concepts)
        return {
            "messages": messages + [AIMessage(content=answer)],
            "concepts": concepts,
        }

    # Concepts detected this turn by the shared detect_concepts node.
    # Already filtered against state["concepts"] during detection, but
    # keep the known-name guard as defense in depth against duplicates.
    detected: list[dict[str, Any]] = state.get("concepts_detected", [])
    known_names: set[str] = {c["name"] for c in concepts}

    new_concepts: list[dict[str, Any]] = []
    for c in detected:
        if c["name"] not in known_names:
            known_names.add(c["name"])
            new_concepts.append(c)

    if not new_concepts:
        return {}

    # Save teaching content to the dashboard (not terminal).  The
    # per-concept Mermaid diagram comes straight from the detection
    # result — previously the teacher node re-detected concepts itself
    # and dropped the diagram field, losing the visuals.
    #
    # save_teaching deduplicates by concept identity (slug) + code
    # hash: an unchanged concept re-detected later is a store no-op, so
    # its explanation and diagram stay consistent even when it
    # resurfaces in a different file.
    teaching_entries = []
    for c in new_concepts:
        teaching_entry = {
            "slug": c.get("slug"),
            "concept_name": c["name"],
            "concept_category": c["category"],
            "explanation": c["description"],
            "source_file": c.get("source_file", ""),
            "diagram": c.get("diagram", ""),
            "content_hash": c.get("content_hash", ""),
        }
        save_teaching(session, teaching_entry)
        teaching_entries.append(teaching_entry)

    # Brief notification in terminal — full teaching is on the dashboard.
    # Deliberately lists no concept names here: the terminal stays clean and
    # the user is pointed to the dashboard for explanations.
    count = len(new_concepts)
    teaching_text = (
        f"📚 {count} new coding concept(s) detected! "
        f"They're available with explanations on the dashboard "
        f"(Concepts section)."
    )

    return {
        "messages": messages + [AIMessage(content=teaching_text)],
        "concepts": concepts + new_concepts,
    }


def _is_user_question(text: str) -> bool:
    """Check if the user's message looks like a question about concepts."""
    text_lower = text.lower().strip()
    question_indicators = [
        "what is", "what are", "what does", "what's",
        "how does", "how do", "how to", "how can",
        "why", "when should", "when do", "when to",
        "can you explain", "tell me about", "describe",
        "difference between", "vs", "versus",
        "how does this work", "explain this",
    ]
    return any(indicator in text_lower for indicator in question_indicators)


def _answer_user_question(question: str, concepts: list[dict[str, Any]]) -> str:
    """Answer a user's question using the LLM, with concept context."""
    api_key = resolve_api_key()
    if not api_key:
        return "I need an API key to answer questions. Please set GROQ_API_KEY."

    # Build context from known concepts
    concept_context = ""
    if concepts:
        concept_lines = []
        for c in concepts[-10:]:  # Last 10 concepts for context
            concept_lines.append(
                f"- {c['name']} ({c.get('category', 'General')}): "
                f"{c.get('description', '')}"
            )
        concept_context = "\n".join(concept_lines)

    system_prompt = (
        "You are a helpful coding teacher. Answer the user's question about "
        "programming concepts. Be clear, concise, and educational. "
        "Use examples when helpful."
    )

    if concept_context:
        system_prompt += f"\n\nRecent concepts in the user's code:\n{concept_context}"

    try:
        client = get_client()
        completion = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ],
            max_completion_tokens=1024,
        )
        return completion.choices[0].message.content or "I couldn't generate an answer."
    except Exception as exc:
        return f"(Error answering question: {exc})"
