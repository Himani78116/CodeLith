"""Teacher Agent — monitors coding sessions and teaches concepts.

When the coding agent writes or edits files, the teacher agent analyzes
the changes to identify programming concepts (hooks, patterns, paradigms)
and generates explanations for the user.

Concepts are extracted from tool-call arguments (file contents) and
matched against a registry of known patterns.  Unrecognised but
interesting code is passed to the LLM for identification.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from backend.llm.client import DEFAULT_MODEL, resolve_api_key, get_client

# ---------------------------------------------------------------------------
# Concept registry — known patterns and their short explanations
# ---------------------------------------------------------------------------

CONCEPT_PATTERNS: dict[str, dict[str, str]] = {
    # React hooks
    "useEffect": {
        "name": "useEffect",
        "category": "React Hook",
        "description": (
            "A React hook that runs side effects after render. "
            "Commonly used for data fetching, subscriptions, and DOM manipulation. "
            "Accepts a cleanup function and a dependency array to control re-runs."
        ),
        "diagram": (
            "flowchart LR\n"
            "    R[Render] --> E[Run effect]\n"
            "    E --> D{deps changed?}\n"
            "    D -- yes --> E\n"
            "    D -- no --> S[Skip]\n"
            "    E --> C[Cleanup fn]\n"
            "    C --> R"
        ),
    },
    "useState": {
        "name": "useState",
        "category": "React Hook",
        "description": (
            "A React hook that adds state to a functional component. "
            "Returns a state value and a setter function. "
            "Re-renders the component when the state changes."
        ),
        "diagram": (
            "flowchart LR\n"
            "    S[Current state] --> C[Component renders]\n"
            "    C --> U[User event calls setter]\n"
            "    U --> N[State updated]\n"
            "    N --> C"
        ),
    },
    "useMemo": {
        "name": "useMemo",
        "category": "React Hook",
        "description": (
            "A React hook that memoizes an expensive computation. "
            "Only recalculates when its dependencies change, "
            "preventing unnecessary re-renders."
        ),
        "diagram": (
            "flowchart LR\n"
            "    R[Render] --> Q{deps changed?}\n"
            "    Q -- yes --> F[Recompute value]\n"
            "    Q -- no --> M[Reuse cached value]\n"
            "    F --> M"
        ),
    },
    "useCallback": {
        "name": "useCallback",
        "category": "React Hook",
        "description": (
            "A React hook that memoizes a callback function. "
            "Useful when passing callbacks to child components that "
            "depend on referential equality."
        ),
        "diagram": (
            "flowchart LR\n"
            "    R[Render] --> Q{deps changed?}\n"
            "    Q -- yes --> F[New function identity]\n"
            "    Q -- no --> M[Same function identity]\n"
            "    M --> P[Child skips re-render]\n"
            "    F --> P"
        ),
    },
    "useRef": {
        "name": "useRef",
        "category": "React Hook",
        "description": (
            "A React hook that creates a mutable ref object. "
            "Persists across renders without causing re-renders. "
            "Commonly used for DOM access and storing previous values."
        ),
        "diagram": (
            "flowchart LR\n"
            "    R[Render] --> B[Read ref.current]\n"
            "    B --> W[Write ref.current]\n"
            "    W --> N[No re-render] --> R"
        ),
    },
    "useContext": {
        "name": "useContext",
        "category": "React Hook",
        "description": (
            "A React hook that reads values from the nearest Context Provider. "
            "Avoids prop drilling by letting components access shared state."
        ),
        "diagram": (
            "flowchart TD\n"
            "    P[Provider holds value] --> A[Component A]\n"
            "    A --> B[Component B]\n"
            "    B --> C[useContext reads value]\n"
            "    C -.no prop drilling.-> P"
        ),
    },
    # JavaScript / TypeScript patterns
    "async function": {
        "name": "Async/Await",
        "category": "Asynchronous Pattern",
        "description": (
            "Syntactic sugar over Promises. An async function returns a "
            "Promise and can use 'await' to pause until a Promise resolves, "
            "making asynchronous code read like synchronous code."
        ),
        "diagram": (
            "sequenceDiagram\n"
            "    participant C as Caller\n"
            "    participant F as async fn\n"
            "    C->>F: call (returns Promise)\n"
            "    F-->>C: promise pending\n"
            "    Note over F: awaits I/O...\n"
            "    F-->>C: resolve with value\n"
            "    C->>C: continue after await"
        ),
    },
    "Promise": {
        "name": "Promises",
        "category": "Asynchronous Pattern",
        "description": (
            "An object representing the eventual completion or failure of "
            "an asynchronous operation.  Chains of .then()/.catch() handle "
            "success and error paths."
        ),
        "diagram": (
            "stateDiagram-v2\n"
            "    [*] --> pending\n"
            "    pending --> fulfilled: .then()\n"
            "    pending --> rejected: error\n"
            "    rejected --> [*]: .catch()\n"
            "    fulfilled --> [*]"
        ),
    },
    "export default": {
        "name": "Default Export",
        "category": "Module System",
        "description": (
            "ES module syntax that marks one value as the module's primary "
            "export.  Importers can name it anything: import Foo from './mod'."
        ),
        "diagram": (
            "flowchart LR\n"
            "    M[Module] -- default export --> V[One primary value]\n"
            "    V --> I1[import Foo from mod]\n"
            "    V --> I2[import Bar from mod]\n"
            "    I1 -.any name works.-> V"
        ),
    },
    "interface ": {
        "name": "TypeScript Interface",
        "category": "TypeScript",
        "description": (
            "Defines the shape of an object — its properties and their types. "
            "Interfaces are checked at compile time and erased in the "
            "generated JavaScript."
        ),
        "diagram": (
            "flowchart LR\n"
            "    I[interface defined] --> TSC[tsc checks types]\n"
            "    TSC --> OK[types match]\n"
            "    TSC --> ERR[type error]\n"
            "    OK --> JS[erased in JS output]"
        ),
    },
    "type ": {
        "name": "TypeScript Type Alias",
        "category": "TypeScript",
        "description": (
            "Gives a name to a type expression (union, intersection, object, "
            "primitive).  Unlike interfaces, type aliases can represent "
            "unions and mapped types."
        ),
        "diagram": (
            "flowchart LR\n"
            "    U[Union type] --> A[type Alias = ...]\n"
            "    I[Intersection] --> A\n"
            "    A --> C[Checked at compile time]"
        ),
    },
    # Python patterns
    "def __init__": {
        "name": "__init__ (Constructor)",
        "category": "Python OOP",
        "description": (
            "The constructor method for a Python class.  Called when a new "
            "instance is created.  Initializes the object's attributes."
        ),
        "diagram": (
            "sequenceDiagram\n"
            "    participant U as User code\n"
            "    participant C as Class\n"
            "    U->>C: MyClass(args)\n"
            "    C->>C: __init__(self, args)\n"
            "    C-->>U: instance with attributes set"
        ),
    },
    "async def": {
        "name": "Python Async Functions",
        "category": "Asynchronous Pattern",
        "description": (
            "Defines a coroutine that can be awaited.  Used with asyncio "
            "for non-blocking I/O operations like network requests and "
            "file access."
        ),
        "diagram": (
            "sequenceDiagram\n"
            "    participant L as Event loop\n"
            "    participant C as Coroutine\n"
            "    L->>C: start coroutine\n"
            "    C-->>L: await I/O (yield)\n"
            "    L->>C: I/O done, resume\n"
            "    C-->>L: return result"
        ),
    },
    "decorator": {
        "name": "Decorators",
        "category": "Python Pattern",
        "description": (
            "Functions that modify other functions or classes.  Applied with "
            "@syntax above the target.  Common uses: logging, caching, "
            "authentication checks."
        ),
        "diagram": (
            "sequenceDiagram\n"
            "    participant C as Caller\n"
            "    participant W as Wrapper\n"
            "    participant F as Original fn\n"
            "    C->>W: call decorated fn\n"
            "    W->>F: delegate\n"
            "    F-->>W: result\n"
            "    W-->>C: result (plus extra behavior)"
        ),
    },
    # General patterns
    "class ": {
        "name": "Classes / OOP",
        "category": "Object-Oriented Programming",
        "description": (
            "Blueprints for creating objects.  Combine state (attributes) "
            "and behavior (methods) into a single unit.  Support "
            "inheritance, encapsulation, and polymorphism."
        ),
        "diagram": (
            "flowchart TD\n"
            "    B[Base class] --> D[Derived class]\n"
            "    D --> O[Instance]\n"
            "    B -.inheritance.-> D\n"
            "    D -.method reuse.-> O"
        ),
    },
    "try:": {
        "name": "Try/Except (Error Handling)",
        "category": "Error Handling",
        "description": (
            "Gracefully handles runtime errors.  Code in the 'try' block "
            "runs normally; if an exception occurs, control jumps to "
            "'except' instead of crashing."
        ),
        "diagram": (
            "flowchart TD\n"
            "    T[Try block] --> E{exception?}\n"
            "    E -- no --> N[continue normally]\n"
            "    E -- yes --> X[Except block]\n"
            "    X --> N"
        ),
    },
    "switch": {
        "name": "Switch Statement",
        "category": "Control Flow",
        "description": (
            "Multi-way branching on one value.  Each 'case' matches a "
            "possible value and runs its block; 'default' handles anything "
            "else.  Cleaner than long if/else-if chains on the same value."
        ),
        "diagram": (
            "flowchart TD\n"
            "    V[Value to match] --> C1{case 1}\n"
            "    C1 -- match --> B1[Run block 1]\n"
            "    C1 -- no --> C2{case 2}\n"
            "    C2 -- match --> B2[Run block 2]\n"
            "    C2 -- no --> D[Default block]"
        ),
    },
    " ? ": {
        "name": "Ternary Operator",
        "category": "Control Flow",
        "description": (
            "Inline conditional: 'condition ? a : b' evaluates to 'a' when "
            "the condition is true, otherwise 'b'.  A compact alternative "
            "to a two-branch if/else used inside expressions."
        ),
        "diagram": (
            "flowchart LR\n"
            "    C{condition?} -- true --> A[value a]\n"
            "    C -- false --> B[value b]\n"
            "    A --> R[result]\n"
            "    B --> R"
        ),
    },
    "import ": {
        "name": "Imports / Modules",
        "category": "Module System",
        "description": (
            "Brings code from other files or packages into the current "
            "namespace.  Enables code reuse and separation of concerns."
        ),
        "diagram": (
            "flowchart LR\n"
            "    M[Other module] --> N[import brings names here]\n"
            "    N --> U[Use without redefining]\n"
            "    P[Package] --> N"
        ),
    },
    "lambda": {
        "name": "Lambda Functions",
        "category": "Functional Programming",
        "description": (
            "Anonymous, inline functions defined with the 'lambda' keyword. "
            "Useful for short callbacks in map(), filter(), and sorted()."
        ),
        "diagram": (
            "flowchart LR\n"
            "    A[lambda x: expression] --> C[Passed as callback]\n"
            "    C --> H[HOF: map, filter, sorted]\n"
            "    H --> R[Result per element]"
        ),
    },
    "map(": {
        "name": "map()",
        "category": "Functional Programming",
        "description": (
            "Applies a function to every element of an iterable, returning "
            "a new iterable of results.  Often combined with list() to "
            "produce a list."
        ),
        "diagram": (
            "flowchart LR\n"
            "    I[1, 2, 3] --> M[map fn]\n"
            "    M --> O[fn 1, fn 2, fn 3]\n"
            "    O --> L[list gathers results]"
        ),
    },
    "filter(": {
        "name": "filter()",
        "category": "Functional Programming",
        "description": (
            "Returns an iterable of elements for which the predicate "
            "function returned True.  Useful for selecting a subset of data."
        ),
        "diagram": (
            "flowchart LR\n"
            "    I[All elements] --> P{predicate true?}\n"
            "    P -- yes --> K[Kept]\n"
            "    P -- no --> D[Dropped]"
        ),
    },
    "querySelector": {
        "name": "DOM Querying",
        "category": "DOM / Browser API",
        "description": (
            "Selects a single element in the DOM using a CSS selector. "
            "querySelectorAll() selects all matching elements."
        ),
        "diagram": (
            "flowchart TD\n"
            "    S[CSS selector string] --> D[DOM tree search]\n"
            "    D --> F[First matching element]\n"
            "    D --> A[querySelectorAll: all matches]"
        ),
    },
    "addEventListener": {
        "name": "Event Listeners",
        "category": "DOM / Browser API",
        "description": (
            "Registers a callback that runs when a specific event fires on "
            "an element (click, submit, keydown, etc.).  Crucial for "
            "interactive web applications."
        ),
        "diagram": (
            "sequenceDiagram\n"
            "    participant U as User\n"
            "    participant E as Element\n"
            "    participant CB as Callback\n"
            "    U->>E: click / keydown\n"
            "    E->>CB: invoke listener\n"
            "    CB-->>E: handle event"
        ),
    },
    "fetch(": {
        "name": "Fetch API",
        "category": "Networking",
        "description": (
            "Makes HTTP requests from the browser or Node.js.  Returns a "
            "Promise that resolves to a Response object.  Typically "
            "combined with .json() to parse the body."
        ),
        "diagram": (
            "sequenceDiagram\n"
            "    participant A as App\n"
            "    participant N as Network\n"
            "    A->>N: fetch(url)\n"
            "    N-->>A: Promise<Response>\n"
            "    A->>N: response.json()\n"
            "    N-->>A: parsed data"
        ),
    },
}


@dataclass
class DetectedConcept:
    """A concept identified from code."""

    name: str
    category: str
    description: str
    source_file: str = ""
    line_range: tuple[int, int] = (0, 0)
    # Optional Mermaid diagram definition rendered on the dashboard.
    diagram: str = ""


# ---------------------------------------------------------------------------
# Detection engine
# ---------------------------------------------------------------------------

def detect_concepts_from_file(file_path: str, content: str) -> list[DetectedConcept]:
    """Scan *content* for known concept patterns and return matches."""
    concepts: list[DetectedConcept] = []
    seen: set[str] = set()

    lines = content.splitlines()
    for line_no, line in enumerate(lines, start=1):
        for pattern, info in CONCEPT_PATTERNS.items():
            if pattern in line and info["name"] not in seen:
                seen.add(info["name"])
                concepts.append(
                    DetectedConcept(
                        name=info["name"],
                        category=info["category"],
                        description=info["description"],
                        source_file=file_path,
                        line_range=(line_no, line_no),
                        diagram=info.get("diagram", ""),
                    )
                )

    return concepts


def detect_concepts_from_tool_calls(
    tool_calls: list[dict[str, Any]],
) -> list[DetectedConcept]:
    """Analyze a batch of tool-call dicts (from the coding agent) and
    return any detected concepts.

    Each tool call is expected to have ``function.name`` and
    ``function.arguments`` (JSON string) with keys like ``file_path``
    and ``content`` (for write_file) or ``old_string``/``new_string``
    (for edit_file).
    """
    concepts: list[DetectedConcept] = []
    seen: set[str] = set()

    for tc in tool_calls:
        fn = tc.get("function", {})
        name = fn.get("name", "")
        try:
            args = json.loads(fn.get("arguments", "{}"))
        except (json.JSONDecodeError, TypeError):
            continue

        # Gather the text to scan
        text_to_scan = ""
        file_path = ""

        if name == "write_file":
            file_path = args.get("file_path", "")
            text_to_scan = args.get("content", "")
        elif name == "edit_file":
            file_path = args.get("file_path", "")
            text_to_scan = args.get("new_string", "")
        elif name == "read_file":
            # We don't detect concepts from reads
            continue
        else:
            continue

        if not text_to_scan:
            continue

        detected = detect_concepts_from_file(file_path, text_to_scan)
        for c in detected:
            if c.name not in seen:
                seen.add(c.name)
                concepts.append(c)

    return concepts


# ---------------------------------------------------------------------------
# LLM-enhanced detection (for patterns not in the registry)
# ---------------------------------------------------------------------------

LLM_DETECT_PROMPT = """\
You are a code-analysis assistant.  Given the following code snippet,
list the key programming concepts, patterns, or techniques used.
Return ONLY a JSON array of objects with keys: "name", "category",
"description", "diagram".
If there are no notable concepts, return an empty array [].

The "diagram" value must be a small, valid Mermaid diagram definition
(flowchart, sequenceDiagram, or stateDiagram-v2) that visually explains
the concept in 3-6 nodes.  Use simple ASCII labels, wrap each label in
square brackets (e.g. A[Label]), and never put parentheses or special
characters inside labels.  If no diagram makes sense, use an empty string.

Code file: {file_path}
```{lang}
{code}
```
"""

DIAGRAM_BACKFILL_PROMPT = """\
For each concept below, produce ONE small, valid Mermaid diagram
(flowchart, sequenceDiagram, or stateDiagram-v2) that visually explains
it in 3-6 nodes.  Use simple ASCII labels, wrap each label in square
brackets (e.g. A[Label]), and never put parentheses or special
characters inside labels.

Concepts:
{concepts}

Return ONLY a JSON object mapping each concept name to its Mermaid
diagram string (use "" only if no diagram can make sense).
"""


def _norm_concept_key(name: str) -> str:
    """Normalize a concept name for tolerant matching.

    Models echoing the prompt's '- Name (Category): ...' format tend to
    return JSON keys like ``"DOM Manipulation (DOM / Browser API)"``
    instead of the bare concept name — compare on the part before the
    first parenthesis, lowercased.
    """
    base = name.split("(", 1)[0]
    return " ".join(base.lower().split())


def _backfill_diagrams(concepts: list[DetectedConcept]) -> None:
    """Ask the LLM for diagrams for concepts detected without one.

    Models sometimes return the concept list but skip the "diagram"
    field (nondeterministically).  One focused follow-up call recovers
    most of those cases.  Best-effort: any failure leaves the diagrams
    empty and the text explanation remains the fallback.

    Mutates *concepts* in place.
    """
    api_key = resolve_api_key()
    if not api_key:
        return

    concept_lines = [
        f"- {c.name} ({c.category}): {c.description[:120]}"
        for c in concepts
    ]
    prompt = DIAGRAM_BACKFILL_PROMPT.format(concepts="\n".join(concept_lines))

    try:
        client = get_client()
        completion = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            # gpt-oss spends most of its budget on reasoning tokens before
            # writing content — 1024 truncated the JSON mid-output
            # (finish_reason: length).  2048 matches the detection call,
            # which is proven to leave room for the full answer.
            max_completion_tokens=2048,
        )
        raw = (completion.choices[0].message.content or "").strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
        diagrams = json.loads(raw)
        if not isinstance(diagrams, dict):
            return
        # Tolerant lookup: models may return keys like
        # "Name (Category)" instead of the bare concept name.
        by_key = {_norm_concept_key(k): v for k, v in diagrams.items()}
        for c in concepts:
            value = by_key.get(_norm_concept_key(c.name), "")
            if isinstance(value, str) and value.strip():
                c.diagram = value.strip()
    except Exception:  # noqa: BLE001 - best-effort backfill only
        return


def detect_concepts_with_llm(
    file_path: str,
    content: str,
    known_names: set[str],
) -> list[DetectedConcept]:
    """Ask the LLM to identify concepts not already in our registry.

    Falls back gracefully if the API key is missing or the call fails.
    """
    api_key = resolve_api_key()
    if not api_key:
        return []

    # Determine language hint from extension
    ext = file_path.rsplit(".", 1)[-1] if "." in file_path else ""
    lang_map = {
        "py": "python",
        "js": "javascript",
        "ts": "typescript",
        "tsx": "tsx",
        "jsx": "jsx",
        "rs": "rust",
        "go": "go",
    }
    lang = lang_map.get(ext, "")

    # Truncate to avoid huge prompts
    if len(content) > 4000:
        content = content[:4000] + "\n... (truncated)"

    prompt = LLM_DETECT_PROMPT.format(
        file_path=file_path, lang=lang, code=content
    )

    try:
        client = get_client()
        completion = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            # Diagrams per concept make the output longer than plain
            # detection, so allow more completion tokens here.
            max_completion_tokens=2048,
        )
        raw = completion.choices[0].message.content or "[]"
        # Extract JSON array from the response (handle markdown fences)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
        concepts_raw = json.loads(raw)
    except Exception:  # noqa: BLE001
        return []

    concepts: list[DetectedConcept] = []
    for item in concepts_raw:
        name = item.get("name", "")
        if not name or name in known_names:
            continue
        concepts.append(
            DetectedConcept(
                name=name,
                category=item.get("category", "General"),
                description=item.get("description", ""),
                source_file=file_path,
                diagram=item.get("diagram", "") or "",
            )
        )

    # Models sometimes skip the diagram field — recover with one
    # focused follow-up call before giving up on a visual.
    missing = [c for c in concepts if not c.diagram]
    if missing:
        _backfill_diagrams(missing)

    return concepts


# ---------------------------------------------------------------------------
# Teacher Agent node (for LangGraph)
# ---------------------------------------------------------------------------


def teacher_agent_node(state: dict[str, Any]) -> dict[str, Any]:
    """LangGraph node: analyze the coding agent's latest output for concepts.

    Expects ``state["messages"]`` to contain the full conversation so far,
    including tool calls from the coding agent.

    Expects ``state["tool_calls_log"]`` to be a list of tool-call dicts
    produced by the coding agent during its last turn.

    Saves teaching content to the dashboard (via database) rather than
    printing it in the terminal.  Only a brief notification is shown
    in the terminal; the full teaching is available on the dashboard.

    When the user asks a question in the terminal, the teacher agent
    answers there directly.
    """
    from backend.database.concepts import save_teaching

    messages: list[BaseMessage] = state.get("messages", [])
    tool_calls_log: list[dict[str, Any]] = state.get("tool_calls_log", [])
    concepts: list[dict[str, Any]] = state.get("concepts", [])
    session: str = state.get("session", "default")
    mode_config: dict[str, Any] = state.get("current_mode_config") or {}
    llm_detection: bool = bool(mode_config.get("llm_detection", True))

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

    # Collect known concept names so we don't re-teach
    known_names: set[str] = {c["name"] for c in concepts}

    # 1. Detect from tool calls (registry-based)
    detected = detect_concepts_from_tool_calls(tool_calls_log)

    # 2. Also try LLM detection for code we've written (mode-gated:
    # slower but more thorough — skipped in autonomous mode)
    for tc in tool_calls_log if llm_detection else []:
        fn = tc.get("function", {})
        name = fn.get("name", "")
        try:
            args = json.loads(fn.get("arguments", "{}"))
        except (json.JSONDecodeError, TypeError):
            continue

        if name == "write_file":
            file_path = args.get("file_path", "")
            content = args.get("content", "")
            if content:
                llm_detected = detect_concepts_with_llm(
                    file_path, content, known_names
                )
                detected.extend(llm_detected)

    # Build teaching content
    if not detected:
        return {}

    new_concepts: list[dict[str, Any]] = []
    for c in detected:
        if c.name not in known_names:
            known_names.add(c.name)
            concept_dict = {
                "name": c.name,
                "category": c.category,
                "description": c.description,
                "source_file": c.source_file,
            }
            new_concepts.append(concept_dict)

    if not new_concepts:
        return {}

    # Save teaching content to the dashboard (not terminal)
    teaching_entries = []
    for c in new_concepts:
        teaching_entry = {
            "concept_name": c["name"],
            "concept_category": c["category"],
            "explanation": c["description"],
            "source_file": c.get("source_file", ""),
            "diagram": c.get("diagram", ""),
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
