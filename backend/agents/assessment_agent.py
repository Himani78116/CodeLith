"""Assessment Agent — generates Socratic questions based on detected concepts.

When the coding agent uses a programming concept (e.g. useState, async/await),
this agent generates a question to test the user's understanding.  Questions
are stored for the dashboard to display — not printed in the terminal.

The teacher agent then saves the teaching content to the dashboard as well.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from backend.agents.teacher_agent import (
    detect_concepts_from_tool_calls,
    detect_concepts_with_llm,
    DetectedConcept,
)
from backend.llm.client import DEFAULT_MODEL, resolve_api_key, get_client

# ---------------------------------------------------------------------------
# Socratic question templates
# ---------------------------------------------------------------------------

QUESTION_TEMPLATES: dict[str, list[str]] = {
    "useState": [
        "Why are we using useState here instead of a regular variable?",
        "What happens when we call the setter function from useState?",
        "When would you NOT want to use useState?",
    ],
    "useEffect": [
        "What does the dependency array control in this useEffect?",
        "Why do we need a cleanup function here?",
        "What happens if we omit the dependency array entirely?",
    ],
    "useMemo": [
        "What problem does useMemo solve in this component?",
        "How does useMemo differ from just calling the function directly?",
        "When would useMemo actually hurt performance instead of helping?",
    ],
    "useCallback": [
        "Why are we wrapping this function in useCallback?",
        "What would happen if we passed the function directly without useCallback?",
        "When is useCallback unnecessary?",
    ],
    "useRef": [
        "Why use useRef instead of useState for this value?",
        "What's the key difference between useRef and useState in terms of re-renders?",
        "When would you reach for useRef over useState?",
    ],
    "useContext": [
        "What problem does useContext solve compared to prop drilling?",
        "When might useContext cause performance issues?",
        "How does the context value get updated?",
    ],
    "async/await": [
        "Why do we use async/await here instead of .then() chains?",
        "What happens if we forget to await this promise?",
        "How does error handling work with async/await?",
    ],
    "Promises": [
        "What are the three states of a Promise?",
        "How does Promise.all differ from Promise.race?",
        "What happens when a Promise rejects and we don't catch it?",
    ],
    "Default Export": [
        "What's the difference between a default export and a named export?",
        "Why might you choose one over the other?",
        "Can a file have multiple default exports?",
    ],
    "TypeScript Interface": [
        "What's the difference between an interface and a type alias?",
        "Why define an interface if TypeScript can infer types?",
        "When would you extend an interface instead of using intersection types?",
    ],
    "Python OOP": [
        "Why do we use __init__ instead of a constructor method?",
        "What does 'self' represent in a Python class?",
        "When would you use a class method vs an instance method?",
    ],
    "Error Handling": [
        "Why wrap this code in try/except instead of letting it fail?",
        "What's the difference between catching Exception vs a specific error?",
        "When is it better to let an exception propagate instead of catching it?",
    ],
    "Decorators": [
        "What does this decorator modify about the function's behavior?",
        "How does @decorator syntax differ from calling decorator(func) directly?",
        "When might you write a custom decorator vs using a built-in one?",
    ],
    "Lambda Functions": [
        "Why use a lambda here instead of a regular function?",
        "What are the limitations of lambda functions in Python?",
        "When would you prefer a named function over a lambda?",
    ],
    "Imports / Modules": [
        "What's the difference between 'import module' and 'from module import X'?",
        "Why might you use __init__.py in a package?",
        "When would you use a relative vs absolute import?",
    ],
    "Classes / OOP": [
        "Why use a class here instead of a module with functions?",
        "What does inheritance give us that composition doesn't?",
        "When is composition preferred over inheritance?",
    ],
    "map()": [
        "Why use map() instead of a for loop here?",
        "What's the difference between map() and a list comprehension?",
        "When might a for loop be clearer than map()?",
    ],
    "filter()": [
        "What does the predicate function need to return for filter()?",
        "How does filter() differ from using a list comprehension with if?",
        "When would you use filter() vs a for loop with conditionals?",
    ],
    "Fetch API": [
        "Why use fetch() instead of XMLHttpRequest?",
        "What happens if we don't await the fetch response?",
        "How does error handling differ between fetch and traditional AJAX?",
    ],
    "DOM Querying": [
        "Why querySelector instead of getElementById?",
        "What's the difference between querySelector and querySelectorAll?",
        "When might direct DOM manipulation be better than a framework?",
    ],
    "Event Listeners": [
        "Why register an event listener instead of using inline HTML handlers?",
        "What's the difference between addEventListener and onclick?",
        "When would you remove an event listener?",
    ],
}

# Fallback generic questions for concepts not in the template
GENERIC_QUESTIONS = [
    "Why did we use {concept_name} here?",
    "What problem does {concept_name} solve in this context?",
    "When would you choose {concept_name} over alternatives?",
]


@dataclass
class Assessment:
    """A pending assessment question for the user."""

    id: str
    concept_name: str
    concept_category: str
    question: str
    source_file: str
    answered: bool = False
    answer: str = ""
    correct: bool = False


def _generate_assessment_id(concept_name: str, source_file: str) -> str:
    """Generate a stable ID for an assessment based on concept + file."""
    import hashlib
    raw = f"{concept_name}:{source_file}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def _get_question(concept_name: str) -> str:
    """Return a Socratic question for the given concept."""
    import random
    templates = QUESTION_TEMPLATES.get(concept_name, GENERIC_QUESTIONS)
    template = random.choice(templates)
    return template.format(concept_name=concept_name)


# ---------------------------------------------------------------------------
# Assessment Agent node (for LangGraph)
# ---------------------------------------------------------------------------


def assessment_agent_node(state: dict[str, Any]) -> dict[str, Any]:
    """LangGraph node: detect concepts from the coding agent's tool calls and
    generate Socratic assessment questions.

    The frequency of questions depends on the session mode:
    - ``learn``: question for every new concept (high frequency)
    - ``pair-programming``: question for roughly 1 in 3 new concepts (low)
    - ``autonomous``: no questions at all

    Expects ``state["tool_calls_log"]`` from the coding agent.
    Expects ``state["concepts"]`` for already-known concepts.
    Expects ``state["session"]`` for storage.
    Expects ``state["current_mode_config"]`` for mode settings.

    Returns:
        - ``pending_assessments``: list of Assessment dicts for the dashboard
        - ``messages``: appends an assessment prompt message
    """
    import random as _random

    from backend.database.concepts import get_pending_assessments, save_assessment

    tool_calls_log: list[dict[str, Any]] = state.get("tool_calls_log", [])
    concepts: list[dict[str, Any]] = state.get("concepts", [])
    session: str = state.get("session", "default")
    messages: list[BaseMessage] = state.get("messages", [])

    # Determine assessment frequency from mode config
    mode_config: dict[str, Any] | None = state.get("current_mode_config")
    if mode_config is not None:
        freq = mode_config.get("assessment_frequency", "high")
    else:
        freq = "high"  # default to generating questions

    # In autonomous mode, skip question generation entirely
    if freq == "none":
        return {}

    # Detect concepts from the coding agent's tool calls
    detected: list[DetectedConcept] = detect_concepts_from_tool_calls(tool_calls_log)

    # Also run LLM-based detection on file contents from write/edit tool calls
    # (pattern-based detection misses many concepts like HTML structure, CSS
    #  patterns, DOM APIs, etc.)
    known_names: set[str] = {c["name"] for c in concepts}
    for tc in tool_calls_log:
        fn = tc.get("function", {})
        name = fn.get("name", "")
        try:
            args = json.loads(fn.get("arguments", "{}"))
        except (json.JSONDecodeError, TypeError):
            continue
        if name == "write_file":
            file_path = args.get("file_path", "")
            content = args.get("content", "")
        elif name == "edit_file":
            file_path = args.get("file_path", "")
            content = args.get("new_string", "")
        else:
            continue
        if not content:
            continue
        llm_detected = detect_concepts_with_llm(file_path, content, known_names)
        for c in llm_detected:
            if c.name not in known_names:
                known_names.add(c.name)
                detected.append(c)

    # Filter to only NEW concepts (not already known)
    new_concepts = [c for c in detected if c.name not in {cc["name"] for cc in concepts}]

    if not new_concepts:
        return {}

    # In low-frequency mode (pair-programming), only ask about ~1 in 3 concepts
    if freq == "low" and len(new_concepts) > 1:
        new_concepts = [c for c in new_concepts if _random.random() < 0.34]
        if not new_concepts:
            return {}

    # Get existing pending assessments to avoid duplicates
    existing = get_pending_assessments(session)
    existing_ids = {a["id"] for a in existing}

    pending: list[dict[str, Any]] = []
    for concept in new_concepts:
        assessment_id = _generate_assessment_id(concept.name, concept.source_file)
        if assessment_id in existing_ids:
            continue

        question = _get_question(concept.name)
        assessment = {
            "id": assessment_id,
            "concept_name": concept.name,
            "concept_category": concept.category,
            "question": question,
            "source_file": concept.source_file,
            "answered": False,
            "answer": "",
            "correct": False,
        }
        save_assessment(session, assessment)
        pending.append(assessment)

    if not pending:
        return {}

    # Build a message that signals new assessments are available
    questions_text = "\n".join(
        f"- {a['question']}" for a in pending
    )
    assessment_msg = (
        f"📚 **New concept(s) detected!** "
        f"I've prepared {len(pending)} question(s) on the dashboard.\n\n"
        f"{questions_text}"
    )

    return {
        "messages": messages + [AIMessage(content=assessment_msg)],
        "pending_assessments": pending,
    }
