"""Session modes — Learn, Pair Programming, and Autonomous.

Each mode changes how the orchestrator routes work through the agent graph:

- **Learn**: Teacher-led.  The teacher agent explains concepts as code is
  written.  The coding agent writes code but always includes explanations.
  The user is in teaching mode — concepts are surfaced prominently.

- **Pair Programming**: Collaborative.  The coding agent writes code and
  the teacher agent identifies concepts in the background.  The user
  drives decisions but the AI assists with implementation.

- **Autonomous**: Full automation.  The coding agent runs with minimal
  explanation.  The teacher agent only surfaces critical concepts.
  Focus is on getting things done.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ModeConfig:
    """Configuration for a session mode."""

    name: str
    description: str
    # Whether the teacher agent runs after every coding agent turn
    teacher_always_runs: bool
    # Whether the coding agent should explain its code
    agent_explains: bool
    # Whether to use LLM-based concept detection (slower but more thorough)
    llm_detection: bool
    # Whether to surface concepts in real-time to the user
    surface_concepts: bool
    # Max tool rounds for the coding agent (higher = more autonomous)
    max_tool_rounds: int
    # System prompt suffix to append to the coding agent's prompt
    prompt_suffix: str
    # Assessment frequency: "high" = question for every new concept,
    # "low" = question for ~1 in 3 new concepts, "none" = no questions
    assessment_frequency: str = "high"


LEARN_MODE = ModeConfig(
    name="learn",
    description=(
        "Teacher-led mode.  Concepts are explained as code is written.  "
        "Great for learning new languages or frameworks."
    ),
    teacher_always_runs=True,
    agent_explains=True,
    llm_detection=True,
    surface_concepts=True,
    max_tool_rounds=3,
    assessment_frequency="high",
    prompt_suffix=(
        "\n\n## LEARN MODE\n"
        "You are in Learn Mode.  After writing or editing code, briefly "
        "explain what you did and why.  Highlight the key concepts used.  "
        "Keep explanations clear and educational — the user is learning."
    ),
)

PAIR_PROGRAMMING_MODE = ModeConfig(
    name="pair-programming",
    description=(
        "Collaborative mode.  You code together with the user.  "
        "The AI assists with implementation while the user drives."
    ),
    teacher_always_runs=True,
    agent_explains=False,
    llm_detection=True,
    surface_concepts=True,
    max_tool_rounds=5,
    assessment_frequency="low",
    prompt_suffix=(
        "\n\n## PAIR PROGRAMMING MODE\n"
        "You are in Pair Programming Mode.  Work collaboratively with "
        "the user.  Implement what they ask for efficiently.  If a "
        "concept is unusual or noteworthy, mention it briefly."
    ),
)

AUTONOMOUS_MODE = ModeConfig(
    name="autonomous",
    description=(
        "Full automation.  The AI handles everything with minimal "
        "explanation.  Fastest mode for experienced users."
    ),
    teacher_always_runs=False,
    agent_explains=False,
    llm_detection=False,
    surface_concepts=True,
    max_tool_rounds=7,
    assessment_frequency="none",
    prompt_suffix=(
        "\n\n## AUTONOMOUS MODE\n"
        "You are in Autonomous Mode.  Work efficiently and minimize "
        "explanation.  Focus on producing correct, working code.  "
        "Only mention a concept if it's critical to understanding."
    ),
)

MODES: dict[str, ModeConfig] = {
    "learn": LEARN_MODE,
    "pair-programming": PAIR_PROGRAMMING_MODE,
    "autonomous": AUTONOMOUS_MODE,
}

DEFAULT_MODE = "learn"


def get_mode(name: str) -> ModeConfig:
    """Return the ModeConfig for *name*, or the default mode."""
    return MODES.get(name, MODES[DEFAULT_MODE])


def list_modes() -> list[dict[str, str]]:
    """Return a summary of all available modes."""
    return [
        {"name": m.name, "description": m.description}
        for m in MODES.values()
    ]
