from __future__ import annotations

import argparse
from typing import Optional

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from backend.orchestrator.graph import run_graph

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765

app = FastAPI(title="CodeLith Daemon")

# In-memory conversation history keyed by session id.
# A new CLI session always sends "new_session" first, then subsequent
# messages carry the same session id so context is preserved.
_conversations: dict[str, list[dict]] = {}


class ChatMessage(BaseModel):
    """Payload accepted by the chat endpoint."""

    message: str = ""
    workspace: str = ""  # user's project root
    session: str = "default"  # conversation session id


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

    # Append the new user message to this session's history.
    history = _conversations.setdefault(session_id, [])
    history.append({"role": "user", "content": text})

    reply = run_graph(text, workspace_root=workspace, history=history)

    # Store the assistant reply so the next turn sees it.
    history.append({"role": "assistant", "content": reply})

    return {"message": reply, "session": session_id}


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
