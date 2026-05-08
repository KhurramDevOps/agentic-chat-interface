# Implementation Plan: Service AI API-First Foundation

**Branch**: `001-service-ai-api-first` | **Date**: 2026-05-08 | **Spec**: `/specs/001-service-ai-api-first/spec.md`
**Input**: Feature specification from `/specs/001-service-ai-api-first/spec.md`

## Summary

Establish an API-first foundation for `service-ai` as a FastAPI microservice with strict `uv`-managed dependencies, OpenAI-syntax compatibility routed to Gemini through LiteLLM, mem0-based local agentic memory, asynchronous background processing for long-running media jobs, and streaming-first delivery via SSE/WebSocket endpoints.

## Technical Context

**Language/Version**: Python 3.11+  
**Primary Dependencies**: FastAPI, Uvicorn, LiteLLM, mem0, Pydantic Settings  
**Storage**: mem0 for local dynamic memory only; MongoDB access is prohibited in `service-ai`  
**Testing**: Pytest, `httpx`/FastAPI TestClient for API and streaming tests  
**Target Platform**: Linux/macOS server runtime for containerized microservice deployment  
**Project Type**: Backend web-service (Python FastAPI microservice)  
**Performance Goals**: First stream chunk under 2s for >=95% of valid chat requests in dev-load testing  
**Constraints**: `uv` only for dependency management, no `requirements.txt`, non-blocking background media jobs, streaming-first response delivery  
**Scale/Scope**: Scope limited to `service-ai` implementation tasks for this phase

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Three-environment boundary respected**: PASS. Plan references `frontend`, `gateway-node`, and `service-ai`, but implementation scope is only `service-ai`.
- **Database separation enforced**: PASS. `service-ai` explicitly forbids MongoDB connectivity and uses mem0 local memory only.
- **Non-blocking UX enforced**: PASS. Long-running media operations are delegated to FastAPI background tasks.
- **Streaming-first delivery enforced**: PASS. API contracts include SSE and WebSocket streaming endpoints.
- **Type safety and dependency policy enforced**: PASS. `uv`-only dependency flow and runtime type validation in agent loops are explicit.

## Project Structure

### Documentation (this feature)

```text
specs/001-service-ai-api-first/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
frontend/
gateway-node/
service-ai/
├── pyproject.toml
├── uv.lock
├── .env.example
├── app/
│   ├── main.py
│   ├── core/
│   │   ├── config.py
│   │   └── logging.py
│   ├── api/
│   │   ├── routes/
│   │   │   ├── health.py
│   │   │   ├── chat.py
│   │   │   ├── stream.py
│   │   │   └── media.py
│   │   └── deps.py
│   ├── services/
│   │   ├── litellm_router.py
│   │   ├── memory_service.py
│   │   ├── streaming_service.py
│   │   └── media_worker.py
│   ├── schemas/
│   │   ├── chat.py
│   │   ├── streaming.py
│   │   └── media.py
│   └── workers/
│       └── background_tasks.py
└── tests/
    ├── contract/
    ├── integration/
    └── unit/
```

**Structure Decision**: Keep monorepo boundaries explicit and implement only within `service-ai`, using an `app/` package with route/service/schema separation to support API-first contract work.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |
