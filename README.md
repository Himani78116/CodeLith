# CodeLith
A multi-agent AI mentor that blends coding assistance with adaptive teaching.

## Repository layout

```
CodeLith/
├── frontend/
│   └── dashboard/        # Dashboard web app
├── backend/
│   ├── api/              # HTTP API layer
│   ├── agents/           # Agent implementations
│   ├── orchestrator/     # Agent orchestration / planning
│   ├── tools/            # Tools available to agents
│   ├── database/         # Data access / persistence
│   ├── daemon/           # Local daemon (server + launcher + state)
│   ├── cli/              # Command-line interface
│   └── main.py           # Backend entrypoint
├── vscode-extension/     # VS Code extension
└── README.md
```

## Getting started

### Run the local daemon

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate        # Windows; on macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cd ..
python -m backend.daemon.launcher start   # starts detached if not already running
python -m backend.daemon.launcher status
python -m backend.daemon.launcher stop
```

The daemon keeps its PID/port files in `~/.mentor/`; `launcher start` won't
spawn a second instance while one is running. Sanity-check it:

```bash
curl -X POST http://127.0.0.1:<port>/chat
# => {"message": "Hello from Mentor"}
```
