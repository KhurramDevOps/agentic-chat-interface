# Quickstart: Service AI API-First Foundation

## Prerequisites

- Python 3.11+
- `uv` installed
- Provider credentials available for Gemini/LiteLLM routing

## 1) Install dependencies with `uv`

From repository root:

```bash
cd service-ai
uv sync
```

## 2) Configure environment variables

Create or update service-scoped env file:

```bash
cp .env.example .env
```

Required variables (example names):

- `SERVICE_AI_ENV`
- `LITELLM_MODEL`
- `GOOGLE_API_KEY`
- `MEM0_API_KEY` (if required by selected mem0 backend mode)

## 3) Run the FastAPI service

```bash
uv run uvicorn app.main:app --reload --port 8000
```

## 4) Verify baseline endpoints

- `GET /health` returns `200`
- `POST /v1/chat/completions` accepts OpenAI-style payload
- `POST /v1/chat/stream` returns SSE stream events
- `GET /ws/chat` upgrades to WebSocket
- `POST /v1/media/generate` returns `202` with task id

## 5) Verify non-blocking background behavior

1. Submit media generation request.
2. Confirm immediate `202` response with `task_id`.
3. Poll `GET /v1/media/tasks/{task_id}` until terminal status.
4. Confirm chat traffic remains responsive during media job processing.

## 6) Run tests

```bash
uv run pytest
```
