from __future__ import annotations

import argparse
from typing import Optional

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.orchestrator.graph import run_graph
from backend.orchestrator.modes import list_modes
from backend.database.concepts import (
    load_concepts,
    get_progress,
    clear_concepts,
    get_pending_assessments,
    get_all_assessments,
    submit_assessment_answer,
    get_assessment_progress,
    get_teachings,
)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765

app = FastAPI(title="CodeLith Daemon")

# Allow the Vite dev server (and any localhost origin) to call our API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory conversation history keyed by session id.
# A new CLI session always sends "new_session" first, then subsequent
# messages carry the same session id so context is preserved.
_conversations: dict[str, list[dict]] = {}
MAX_HISTORY_TURNS = 4  # keep last N user+assistant pairs to stay within TPM limits


class ChatMessage(BaseModel):
    """Payload accepted by the chat endpoint."""

    message: str = ""
    workspace: str = ""  # user's project root
    session: str = "default"  # conversation session id
    mode: str = "learn"  # session mode: learn, pair-programming, autonomous


class QuestionMessage(BaseModel):
    """A user question for the dashboard chat."""

    question: str = ""
    session: str = "default"


class AssessmentAnswer(BaseModel):
    """An answer to an assessment question."""

    assessment_id: str
    answer: str
    correct: bool = False
    session: str = "default"


@app.get("/health")
def health() -> dict:
    """Liveness probe."""
    return {"status": "ok"}


@app.post("/chat")
def chat(payload: Optional[ChatMessage] = None) -> dict:
    """Chat endpoint: forward the message (with history) to the graph."""
    if payload is None:
        return {"message": "", "session": "default"}

    text = payload.message
    workspace = payload.workspace or None
    session_id = payload.session or "default"
    mode = payload.mode or "learn"

    # Append the new user message to this session's history.
    history = _conversations.setdefault(session_id, [])
    history.append({"role": "user", "content": text})

    # Trim history to stay within TPM limits (keep last N pairs)
    if len(history) > MAX_HISTORY_TURNS * 2:
        history[:] = history[-MAX_HISTORY_TURNS * 2:]

    result = run_graph(
        text,
        workspace_root=workspace,
        history=history,
        mode=mode,
        session=session_id,
    )

    # Store the assistant reply so the next turn sees it.
    history.append({"role": "assistant", "content": result["reply"]})

    return {
        "message": result["reply"],
        "session": session_id,
        "concepts": result.get("concepts", []),
        "teaching": result.get("teaching", ""),
    }


# --- Dashboard API endpoints ------------------------------------------------


@app.get("/modes")
def modes() -> dict:
    """Return available session modes."""
    return {"modes": list_modes()}


@app.get("/concepts")
def concepts(session: str = "default") -> dict:
    """Return all stored concepts for a session."""
    return {"concepts": load_concepts(session)}


@app.get("/progress")
def progress(session: str = "default") -> dict:
    """Return learning progress summary for a session."""
    return get_progress(session)


@app.post("/question")
def question(payload: Optional[QuestionMessage] = None) -> dict:
    """Answer a user question using the LLM (without file operations)."""
    from backend.llm.client import generate_reply

    if payload is None:
        return {"answer": ""}

    question_text = payload.question
    if not question_text.strip():
        return {"answer": "Please ask a question."}

    answer = generate_reply(question_text)
    return {"answer": answer}


@app.delete("/concepts")
def delete_concepts(session: str = "default") -> dict:
    """Clear all stored concepts for a session."""
    clear_concepts(session)
    return {"status": "cleared"}


# --- Assessment endpoints --------------------------------------------------


@app.get("/assessments")
def assessments(session: str = "default") -> dict:
    """Return all assessments (pending and answered) for a session."""
    return {"assessments": get_all_assessments(session)}


@app.get("/assessments/pending")
def pending_assessments(session: str = "default") -> dict:
    """Return only pending (unanswered) assessments."""
    return {"assessments": get_pending_assessments(session)}


@app.post("/assessments/answer")
def answer_assessment(payload: Optional[AssessmentAnswer] = None) -> dict:
    """Submit an answer to an assessment question."""
    if payload is None:
        return {"status": "error", "message": "No payload provided"}

    result = submit_assessment_answer(
        session=payload.session,
        assessment_id=payload.assessment_id,
        answer=payload.answer,
        correct=payload.correct,
    )

    if result is None:
        return {"status": "error", "message": "Assessment not found"}
    return {"status": "ok", "assessment": result}


@app.get("/assessments/progress")
def assessment_progress(session: str = "default") -> dict:
    """Return assessment performance summary."""
    return get_assessment_progress(session)


# --- Teaching endpoints (for dashboard) ------------------------------------


@app.get("/teachings")
def teachings(session: str = "default") -> dict:
    """Return all teaching entries for a session."""
    return {"teachings": get_teachings(session)}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Stub WebSocket endpoint: accept connections and echo messages back."""
    await websocket.accept()
    try:
        while True:
            message = await websocket.receive_text()
            await websocket.send_text(message)
    except WebSocketDisconnect:
        pass


def run(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    """Serve the daemon app."""
    uvicorn.run(app, host=host, port=port)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="CodeLith local daemon server")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"bind host (default: {DEFAULT_HOST})")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"bind port (default: {DEFAULT_PORT})")
    args = parser.parse_args(argv)
    run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
