# Your Personal AI IT Technician

A Python (FastAPI) web app that acts as an AI IT support engineer. It runs a real
Claude-powered troubleshooting chat with saved sessions, accepts screenshots of
errors, and includes working IT utilities (DNS, IP info, HTTP status, port check,
password strength, and ping/traceroute command generators).

## Features

- Systematic troubleshooting chat (asks questions, narrows causes, never claims a fix without confirmation)
- Screenshot upload and analysis (Claude vision)
- Saved conversations: list, continue, delete, and start new sessions
- Streaming AI responses with Markdown and code blocks that have copy buttons
- Dark and light themes, responsive layout
- Utilities that actually perform their functions (see `tools.py`)

## Setup

Requires Python 3.10+.

```bash
cd it-technician-agent
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # then put your ANTHROPIC_API_KEY in .env
export $(grep -v '^#' .env | xargs)   # Windows PowerShell: load the variables manually
uvicorn main:app --reload
```



## Configuration

| Variable | Purpose | Default |
|---|---|---|
| `ANTHROPIC_API_KEY` | Your Anthropic API key (required for chat) | none |
| `CLAUDE_MODEL` | Model used for troubleshooting | `claude-sonnet-5-5` |
| `DB_PATH` | SQLite file for saved sessions | `data/it_agent.db` |

## Project layout

```
main.py        FastAPI app, chat streaming, conversation and tool routes
db.py          SQLite storage for conversations and messages
tools.py       Real IT utilities (DNS, IP info, HTTP, ports, passwords, commands)
prompts.py     The IT technician system prompt
static/        Frontend: index.html, style.css, app.js
```

## Security notes

- Keep your API key in `.env` or the environment, never in the frontend.
- The utilities that contact remote hosts (HTTP status, port check) will connect to
  any address you enter. Run the app locally, or put it behind authentication before
  exposing it publicly, so it cannot be used to probe internal networks.
- Passwords sent to the strength checker are evaluated in memory and never stored or logged.
- The command generators only produce command text. They never run anything on your machine.
