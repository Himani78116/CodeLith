"""Concept detection — shared engine used by the assessment and teacher agents.

This module owns the full detection pipeline:

1. **Registry scan** — file contents written/edited by the coding agent are
   matched against :data:`CONCEPT_PATTERNS`, a curated registry of known
   patterns, each with a name, category, description, and (usually) a Mermaid
   diagram.
2. **LLM detection** — for code the registry does not recognise, the LLM
   identifies additional concepts (mode-gated: skipped when
   ``llm_detection`` is off since it costs an LLM call per written file).

The graph runs this once per turn in the ``detect_concepts`` node and stores
the result in ``state["concepts_detected"]``.  The assessment and teacher
agents then read that shared result instead of each re-scanning
``tool_calls_log`` — halving the LLM calls per turn and keeping the teacher
agent's rich per-concept diagram for the dashboard.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from backend.agents.concept_categories import (
    is_valid_category,
    normalize_category,
)
from backend.llm.client import DEFAULT_MODEL, resolve_api_key, get_client

# ---------------------------------------------------------------------------
# Concept registry — known patterns and their short explanations
# ---------------------------------------------------------------------------

CONCEPT_PATTERNS: dict[str, dict[str, str]] = {
    # React hooks
    "useEffect": {
        "name": "useEffect",
        "category": "api",
        "subcategory": "React Hook",
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
        "category": "api",
        "subcategory": "React Hook",
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
        "category": "api",
        "subcategory": "React Hook",
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
        "category": "api",
        "subcategory": "React Hook",
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
        "category": "api",
        "subcategory": "React Hook",
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
        "category": "api",
        "subcategory": "React Hook",
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
        "category": "abstract",
        "subcategory": "Asynchronous Pattern",
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
        "category": "abstract",
        "subcategory": "Asynchronous Pattern",
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
        "category": "abstract",
        "subcategory": "Module System",
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
        "category": "data_model",
        "subcategory": "TypeScript",
        "description": (
            "Defines the shape of an object — its properties and their types. "
            "Interfaces are checked at compile time and erased in the "
            "generated JavaScript."
        ),
        "diagram": (
            "erDiagram\n"
            "    USER {\n"
            "        string id\n"
            "        string email\n"
            "    }\n"
            "    ORDER ||--o{ USER : placed-by"
        ),
    },
    "type ": {
        "name": "TypeScript Type Alias",
        "category": "data_model",
        "subcategory": "TypeScript",
        "description": (
            "Gives a name to a type expression (union, intersection, object, "
            "primitive).  Unlike interfaces, type aliases can represent "
            "unions and mapped types."
        ),
        "diagram": (
            "erDiagram\n"
            "    USER {\n"
            "        string id\n"
            "        string status\n"
            "    }\n"
            "    USER ||--o| PROFILE : one-to-optional"
        ),
    },
    # Python patterns
    "def __init__": {
        "name": "__init__ (Constructor)",
        "category": "structure",
        "subcategory": "Python OOP",
        "description": (
            "The constructor method for a Python class.  Called when a new "
            "instance is created.  Initializes the object's attributes."
        ),
        "diagram": (
            "classDiagram\n"
            "    class Animal {\n"
            "        +String name\n"
            "        +__init__(name)\n"
            "        +speak()\n"
            "    }\n"
            "    Animal : constructor initializes attributes"
        ),
    },
    "async def": {
        "name": "Python Async Functions",
        "category": "abstract",
        "subcategory": "Asynchronous Pattern",
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
        "category": "abstract",
        "subcategory": "Python Pattern",
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
    "for ": {
        "name": "For Loops",
        "category": "algorithm",
        "subcategory": "Control Flow",
        "description": (
            "Definite iteration over a sequence (range, list, string, or "
            "iterator).  The loop variable takes each element in turn; "
            "'break' and 'continue' control the flow."
        ),
        "diagram": (
            "flowchart LR\n"
            "    S[Start] --> C{more items?}\n"
            "    C -- yes --> B[run body] --> N[next item] --> C\n"
            "    C -- no --> D[done]"
        ),
    },
    "while ": {
        "name": "While Loops",
        "category": "algorithm",
        "subcategory": "Control Flow",
        "description": (
            "Indefinite iteration: the body runs as long as the condition "
            "holds.  Requires the condition to eventually become false "
            "(or a break) to avoid an infinite loop."
        ),
        "diagram": (
            "flowchart LR\n"
            "    S[Start] --> C{condition true?}\n"
            "    C -- yes --> B[run body] --> C\n"
            "    C -- no --> D[done]"
        ),
    },
    "class ": {
        "name": "Classes / OOP",
        "category": "structure",
        "subcategory": "Object-Oriented Programming",
        "description": (
            "Blueprints for creating objects.  Combine state (attributes) "
            "and behavior (methods) into a single unit.  Support "
            "inheritance, encapsulation, and polymorphism."
        ),
        "diagram": (
            "classDiagram\n"
            "    class Animal {\n"
            "        +String name\n"
            "        +speak()\n"
            "    }\n"
            "    Animal <|-- Dog : inheritance\n"
            "    Animal : +attributes\n"
            "    Animal : +methods()"
        ),
    },
    "try:": {
        "name": "Try/Except (Error Handling)",
        "category": "abstract",
        "subcategory": "Error Handling",
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
        "category": "algorithm",
        "subcategory": "Control Flow",
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
        "category": "algorithm",
        "subcategory": "Control Flow",
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
        "category": "abstract",
        "subcategory": "Module System",
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
        "category": "algorithm",
        "subcategory": "Functional Programming",
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
        "category": "algorithm",
        "subcategory": "Functional Programming",
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
        "category": "algorithm",
        "subcategory": "Functional Programming",
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
        "category": "api",
        "subcategory": "DOM / Browser API",
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
        "category": "api",
        "subcategory": "DOM / Browser API",
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
        "category": "api",
        "subcategory": "Networking",
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
    # Human-readable sub-label (e.g. "React Hook") under the canonical
    # taxonomy ``category`` (e.g. "api").
    subcategory: str = ""
    source_file: str = ""
    line_range: tuple[int, int] = (0, 0)
    # Optional Mermaid diagram definition rendered on the dashboard.
    diagram: str = ""


# ---------------------------------------------------------------------------
# Mermaid syntax validation (lightweight, no parser dependency)
# ---------------------------------------------------------------------------

MERMAID_DIAGRAM_TYPES = (
    "flowchart",
    "classDiagram",
    "sequenceDiagram",
    "erDiagram",
    "stateDiagram-v2",
)

_FENCE_RE = re.compile(r"^\s*```\w*\s*$", re.MULTILINE)

# One general mechanism for every structural check: replace each
# label/quoted span with a neutral placeholder, then validate the
# remaining "skeleton".  A label span is a single-line, well-paired
# (...), [...] or {...} group with no nested delimiters; a quoted span
# honors ``\"`` escapes and may contain brackets of any kind.  Content
# inside a span is exempt from balance checks — this one rule is what
# lets quotes inside labels (``A["say \"hi\""]``) and ER cardinality
# braces (``ORDER ||--o{ USER``) coexist with strict checks outside
# spans, with no per-character exemption logic to keep in sync.
_STRIP_SPAN_RE = re.compile(
    r'"(?:\\.|[^"\\\n])*"'          # quoted span, \" escapes honored
    r"|\([^()\[\]{}\"\n]*\)"        # (...) label
    r"|\[[^()\[\]{}\"\n]*\]"        # [...] label
    r"|\{[^()\[\]{}\"\n]*\}"        # {...} decision-node label
)
_PLACEHOLDER = "\uFFFD"


def _strip_labels(diagram: str) -> str:
    """Stage 1: replace every label/quoted span with a placeholder.

    Single left-to-right pass, quoted spans first so a quote inside a
    label is consumed before label matching ever sees it.  Spans cannot
    cross newlines, so ER relation braces (``||--o{``) survive unpaired
    on their line — correctly, since they are structural there.
    """
    return _STRIP_SPAN_RE.sub(_PLACEHOLDER, diagram)


def is_valid_mermaid(diagram: str) -> bool:
    """Lightweight sanity check that *diagram* parses as Mermaid.

    Two stages:

    1. :func:`_strip_labels` extracts every ``[...]``/``(...)``/``{...}``
       label span and quoted string into placeholders, producing a
       skeleton of pure structural characters.
    2. The skeleton is checked for: a routed diagram-type header,
       balanced ``( )``/``[ ]`` brackets, braces only where they are
       structural (ER relations, class attribute blocks), and no stray
       double quotes outside spans.

    Not a full parser — it catches the failure modes that make the
    dashboard's Mermaid renderer show a syntax error instead of a
    diagram.  Empty/whitespace-only input is invalid: the save path
    treats a blank diagram as "no diagram", but callers who backfill
    need the distinction made explicit.
    """
    if not isinstance(diagram, str) or not diagram.strip():
        return False

    text = _FENCE_RE.sub("", diagram).strip()
    if not text:
        return False
    skeleton = _strip_labels(text)
    lines = skeleton.splitlines()
    if not lines[0].strip().startswith(MERMAID_DIAGRAM_TYPES):
        return False

    first_word = lines[0].strip().split(None, 1)[0]
    braces_structural = first_word in ("erDiagram", "classDiagram")

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("%%"):
            continue

        if not braces_structural and ("{" in stripped or "}" in stripped):
            # Braces surviving the strip are only legal in ER relations
            # and class attribute blocks.
            return False

        depth = 0
        for ch in stripped:
            if ch in "[(":
                depth += 1
            elif ch in ")]":
                depth -= 1
                if depth < 0:
                    return False  # closer before opener
            elif ch == '"':
                return False  # quote outside any span
        if depth != 0:
            return False  # unclosed bracket

    return True


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
                        subcategory=info.get("subcategory", ""),
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

The "category" value MUST be exactly one of these five strings — no
other values, no capitalization changes, no invented labels:
- "algorithm"  — loops, sorting, searching, recursion, big-O reasoning
- "structure"  — classes, interfaces, inheritance, encapsulation, OOP
- "api"        — calls into a defined interface: fetch, DOM, SDKs, hooks
- "data_model" — how data is shaped or moved: schemas, type aliases,
  JSON payloads, ORMs, validation
- "abstract"   — cross-cutting ideas: error handling, modules, async,
  design patterns

The "diagram" value must be a small, valid Mermaid diagram WHOSE TYPE
matches the concept's category — this routing is required:
- "algorithm"  -> flowchart (process steps and decision points)
- "structure"  -> classDiagram (classes, methods, inheritance)
- "api"        -> sequenceDiagram (participants exchanging messages)
- "data_model" -> erDiagram (entities with attributes and relations)
- "abstract"   -> "" (no diagram: the explanation is prose-only; do NOT
  invent one for abstract concepts)
Aim for 3-6 nodes.  Use simple ASCII labels, wrap each label in
square brackets (e.g. A[Label]), and never put parentheses or special
characters inside labels.

Code file: {file_path}
```{lang}
{code}
```
"""

CATEGORY_FIX_PROMPT = """\
Your previous response described programming concepts but some
"category" values were missing or not from the allowed set:
algorithm, structure, api, data_model, abstract.

Re-send ONLY a JSON object mapping each concept name below to an object
with its corrected category, e.g. {{"Concept Name": {{"category":
"api"}}}}.  Choose from the five allowed values only.

Concepts needing a category:
{concepts}
"""

DIAGRAM_BACKFILL_PROMPT = """\
For each concept below, produce ONE small, valid Mermaid diagram whose
TYPE matches the concept's category — flowchart for algorithm,
classDiagram for structure, sequenceDiagram for api, and erDiagram for
data_model.  Aim for 3-6 nodes.  Use simple ASCII labels, wrap each
label in square brackets (e.g. A[Label]), and never put parentheses or
special characters inside labels.

Concepts (name | category | description):
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

    # Abstract concepts are prose-only by design — never backfill a
    # diagram for them.
    concepts = [c for c in concepts if c.category != "abstract"]
    if not concepts:
        return

    concept_lines = [
        f"- {c.name} | {c.category} | {c.description[:120]}"
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
                candidate = value.strip()
                if is_valid_mermaid(candidate):
                    c.diagram = candidate
                # An invalid replacement is worse than none: the
                # dashboard would render a syntax error instead of
                # falling back to prose.  Leave the (invalid) diagram
                # field as-is; the save path strips it.
    except Exception:  # noqa: BLE001 - best-effort backfill only
        return


def _retry_categories(concepts: list[DetectedConcept]) -> None:
    """Ask the LLM to re-tag concepts whose category was missing/invalid.

    ONE corrective call is made, listing only the offending concepts.
    Concepts whose category is still missing or outside the taxonomy are
    rejected by the caller — a detection is never default-filled.
    Mutates *concepts* in place: fixed entries get a canonical category;
    unfixed entries keep ``category == ""`` (invalid) so the caller can
    drop them.
    """
    api_key = resolve_api_key()
    if not api_key:
        return

    concept_lines = [
        f"- {c.name}: {c.description[:120]}"
        for c in concepts
    ]
    prompt = CATEGORY_FIX_PROMPT.format(concepts="\n".join(concept_lines))
    try:
        client = get_client()
        completion = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=1024,
        )
        raw = (completion.choices[0].message.content or "").strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
        fixes = json.loads(raw)
        if not isinstance(fixes, dict):
            return
        # Tolerant lookup: keys may be decorated ("Name (hint)").
        by_key = {_norm_concept_key(k): v for k, v in fixes.items()}
        for c in concepts:
            fix = by_key.get(_norm_concept_key(c.name))
            if isinstance(fix, dict):
                fixed = normalize_category(fix.get("category"))
            elif isinstance(fix, str):
                # Tolerate a bare {"Name": "api"} mapping.
                fixed = normalize_category(fix)
            else:
                fixed = None
            if fixed is not None:
                c.category = fixed
    except Exception:  # noqa: BLE001 - best-effort retry only
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
    needs_category: list[DetectedConcept] = []
    for item in concepts_raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name or name in known_names:
            continue
        description = str(item.get("description", ""))
        diagram = str(item.get("diagram", "") or "")
        raw_category = item.get("category")
        category = normalize_category(raw_category)
        raw_label = (
            str(raw_category).strip() if isinstance(raw_category, str) else ""
        )
        if category is None:
            # Missing or unrecognizable — queue for the corrective retry;
            # never default-fill.
            concept = DetectedConcept(
                name=name,
                category="",
                description=description,
                subcategory=raw_label,
                source_file=file_path,
                diagram=diagram,
            )
            concepts.append(concept)
            needs_category.append(concept)
            continue
        concepts.append(
            DetectedConcept(
                name=name,
                category=category,
                description=description,
                # Keep the model's own label as the human-readable
                # subcategory when it adds detail beyond the slug.
                subcategory=(
                    raw_label if raw_label and raw_label.lower() != category else ""
                ),
                source_file=file_path,
                # Abstract concepts are prose-only: strip any diagram the
                # model emitted anyway so the dashboard never renders a
                # generic one for a genuinely abstract idea.
                diagram=("" if category == "abstract" else diagram),
            )
        )

    # Guard: one corrective retry for concepts whose category was
    # missing or outside the taxonomy, then reject whatever is still
    # invalid.  Responses are never accepted with a default category.
    if needs_category:
        _retry_categories(needs_category)
    valid: list[DetectedConcept] = [
        c for c in concepts if is_valid_category(c.category)
    ]

    # Models sometimes skip the diagram field or emit malformed Mermaid —
    # recover both with one focused follow-up call before giving up on a
    # visual.  Abstract concepts stay prose-only and are excluded from
    # backfill.
    missing = [
        c for c in valid
        if c.category != "abstract"
        and (not c.diagram or not is_valid_mermaid(c.diagram))
    ]
    if missing:
        _backfill_diagrams(missing)

    return valid


# ---------------------------------------------------------------------------
# Graph node — run detection once per turn for both downstream agents
# ---------------------------------------------------------------------------

def detect_concepts(state: dict[str, Any]) -> dict[str, Any]:
    """LangGraph node: detect concepts from the coding agent's tool calls.

    Combines the registry scan with mode-gated LLM detection and writes
    the merged, deduplicated result to ``state["concepts_detected"]``.
    The assessment and teacher agents read that shared result instead of
    re-scanning the tool calls themselves.

    Expects ``state["tool_calls_log"]`` from the coding agent.
    Expects ``state["concepts"]`` for already-known concepts.
    Expects ``state["current_mode_config"]`` for mode settings.

    Returns:
        - ``concepts_detected``: list of dicts with ``name``, ``category``,
          ``description``, ``diagram`` (plus ``source_file``/``line_range``
          where known)
    """
    tool_calls_log: list[dict[str, Any]] = state.get("tool_calls_log", [])
    concepts: list[dict[str, Any]] = state.get("concepts", [])
    mode_config: dict[str, Any] | None = state.get("current_mode_config")

    # 1. Registry-based detection from write/edit tool calls.
    detected: list[DetectedConcept] = []
    seen: set[str] = set()
    for c in detect_concepts_from_tool_calls(tool_calls_log):
        if c.name not in seen:
            seen.add(c.name)
            detected.append(c)

    # 2. LLM detection on file contents from write/edit tool calls
    #    (pattern-based detection misses many concepts like HTML structure,
    #    CSS patterns, DOM APIs, etc.)  Mode-gated: skipped when
    #    llm_detection is off (autonomous mode) since it costs an LLM call
    #    per written file.
    llm_detection: bool = True if mode_config is None else bool(
        mode_config.get("llm_detection", True)
    )
    known_names: set[str] = {c["name"] for c in concepts}
    for tc in (tool_calls_log if llm_detection else []):
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
            if c.name not in known_names and c.name not in seen:
                known_names.add(c.name)
                seen.add(c.name)
                detected.append(c)

    return {
        "concepts_detected": [
            {
                "name": c.name,
                "category": c.category,
                "subcategory": c.subcategory,
                "description": c.description,
                "diagram": c.diagram,
                "source_file": c.source_file,
                "line_range": list(c.line_range),
            }
            for c in detected
        ],
    }
