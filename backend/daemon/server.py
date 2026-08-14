from __future__ import annotations

import argparse

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765

app = FastAPI(title="CodeLith Daemon")


@app.get("/health")
def health() -> dict:
    """Liveness probe."""
    return {"status": "ok"}


@app.post("/chat")
def chat() -> dict:
    """Stub chat endpoint."""
    return {"message": "Hello from Mentor"}


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
