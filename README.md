# CodeLith
An AI mentor that blends coding assistance with adaptive teaching.

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
spawn a second instance while one is running. ### Chat with the CLI

The `mentor` command starts an interactive session that talks to the daemon.
It auto-starts the daemon if it isn't already running, and the daemon keeps
running in the background after the CLI exits:

```bash
pip install -e .                    # exposes the `mentor` command
mentor
```

```
Mentor AI
Mode: Learn

> What is a closure?
A closure is a function that remembers the variables from the scope where it
was defined, even after that scope has finished running...
> exit
```

Exit with `exit`, `quit`, `q`, or Ctrl+C. Check the daemon with
`python -m backend.daemon.launcher status` and stop it with
`python -m backend.daemon.launcher stop`.

### Connect an LLM (Groq)

Replies come from the Groq API (`openai/gpt-oss-120b` by default).

**`.env` file in the project root** (recommended — picked up on the next
   message, no daemon restart needed):

   ```
   # .env
   GROQ_API_KEY=gsk_...
   ```

Then restart the daemon if it is already running:

```bash
python -m backend.daemon.launcher stop
mentor   # auto-starts the daemon
```
