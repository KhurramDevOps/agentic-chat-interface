# service-ai

Agentic AI microservice for the Agentic Chat Interface monorepo.

Built with **FastAPI** · **LiteLLM** · **mem0** · **openai-agents** · managed by **uv**.

---

## Prerequisites

- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/) installed globally

```bash
# Install uv (if not already installed)
pip install uv
# or via Homebrew
brew install uv
```

---

## Setup (under 15 minutes)

```bash
# 1. From the repo root, enter the service directory
cd service-ai

# 2. Install all dependencies (creates .venv automatically)
uv sync

# 3. Copy and configure environment variables
cp .env.example .env
# Edit .env — fill in GEMINI_API_KEY and any other required values
```

---

## Running the service

```bash
# Development — auto-reload on file changes
uv run uvicorn app.main:app --reload

# Via the project script entry point (equivalent to above)
uv run start

# Production — no reload, explicit host/port
APP_ENV=production uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

API docs (Swagger UI) available at `http://localhost:8000/docs` (development only).

---

## Health endpoints

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/health/live` | Liveness probe — is the process up? |
| `GET /api/v1/health/ready` | Readiness probe — is config valid? |
| `GET /api/v1/health` | Combined health summary |

---

## Running tests

```bash
# Run the full test suite
uv run pytest

# Verbose output with test names
uv run pytest -v

# Run a specific test file
uv run pytest tests/contract/test_health.py -v

# Run a specific test class
uv run pytest tests/integration/test_config.py::TestMongoDBSafeguard -v
```

---

## Dependency management

All dependencies are managed exclusively through `uv`. **Do not create or modify `requirements.txt`.**

```bash
# Add a runtime dependency
uv add <package>

# Add a dev-only dependency
uv add --dev <package>

# Remove a dependency
uv remove <package>

# Sync environment to lockfile (after pulling changes)
uv sync
```

---

## Project structure

```
service-ai/
├── app/
│   ├── main.py              # FastAPI app factory + lifespan
│   ├── api/
│   │   ├── deps.py          # Error envelopes, shared dependencies
│   │   └── routes/
│   │       ├── __init__.py  # Central router registration
│   │       └── health.py    # Health / liveness / readiness endpoints
│   ├── core/
│   │   ├── config.py        # Pydantic BaseSettings + MongoDB safeguard
│   │   ├── logging.py       # Structured logging (JSON in prod, text in dev)
│   │   └── type_guards.py   # Runtime type validation for agent payloads
│   ├── agents/              # Triage + domain agents (Phase 4)
│   ├── schemas/             # Pydantic request/response models (Phase 4+)
│   └── workers/             # Background task workers (Phase 5)
└── tests/
    ├── contract/            # API shape / contract tests
    └── integration/         # Config, service, and agent integration tests
```

---

## Constitution compliance

- `service-ai` has **no MongoDB connectivity** — all durable storage belongs to `gateway-node`.
- Local agentic memory uses **mem0** only.
- Long-running jobs run as **FastAPI Background Tasks** — never blocking the request thread.
- All model output is delivered via **SSE or WebSocket** streaming.
- Any attempt to inject a MongoDB URI at startup raises a `ValueError` immediately.
