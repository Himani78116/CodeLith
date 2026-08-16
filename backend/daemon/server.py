from __future__ import annotations

import argparse
from typing import Optional

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765

app = FastAPI(title="CodeLith Daemon")


class ChatMessage(BaseModel):
    """Payload accepted by the chat endpoint."""

    message: str = ""


@app.get("/health")
def health() -> dict:
    """Liveness probe."""
    return {"status": "ok"}


@app.post("/chat")
def chat(payload: Optional[ChatMessage] = None) -> dict:
    """Stub chat endpoint: echo the incoming message back."""
    text = payload.message if payload is not None else ""
    return {"message": f"You said: {text}" if text else "Hello from Mentor"}


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
