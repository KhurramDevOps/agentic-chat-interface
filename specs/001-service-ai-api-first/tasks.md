# Tasks: Service AI API-First Foundation

**Input**: Design documents from `/specs/001-service-ai-api-first/`  
**Prerequisites**: `plan.md` (required), `spec.md` (required), `research.md`, `data-model.md`, `contracts/`

**Tests**: Include focused contract/integration tests for API-first behaviors in `service-ai`.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (`US1`, `US2`, `US3`)
- All file paths are scoped to `service-ai` and feature docs only

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Initialize `service-ai` project structure and `uv`-managed runtime baseline.

- [ ] T001 Create FastAPI app package structure in `service-ai/app/` with subfolders `api/`, `core/`, `agents/`, `schemas/`, and `workers/`
- [ ] T002 Configure `service-ai/pyproject.toml` for FastAPI service metadata and scripts aligned with `uv run`
- [ ] T003 [P] Add required dependencies (`fastapi`, `uvicorn`, `litellm`, `mem0ai`, `openai-agents`) with `uv add` and refresh lockfile
- [ ] T004 [P] Create `service-ai/.env.example` with service-scoped variables for LiteLLM, Gemini, mem0, and runtime mode
- [ ] T005 Implement settings loader and startup config validation in `service-ai/app/core/config.py`
- [ ] T006 Create FastAPI app entrypoint and lifecycle wiring in `service-ai/app/main.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Build shared API and runtime foundations required by all user stories.

**⚠️ CRITICAL**: No user story implementation starts until this phase completes.

- [ ] T007 Implement shared API router registration in `service-ai/app/api/routes/__init__.py`
- [ ] T008 [P] Add standardized API error envelope and exception handlers in `service-ai/app/api/deps.py`
- [ ] T009 [P] Add structured service logging configuration in `service-ai/app/core/logging.py`
- [ ] T010 Implement runtime type-guard utilities for agent payload validation in `service-ai/app/core/type_guards.py`
- [ ] T011 Implement constitution boundary safeguard that rejects direct MongoDB usage in `service-ai/app/core/config.py`

**Checkpoint**: Foundation complete; user stories can proceed.

---

## Phase 3: User Story 1 - Bootstrap `service-ai` FastAPI Runtime (Priority: P1) 🎯 MVP

**Goal**: Deliver a runnable `service-ai` FastAPI service fully managed by `uv`.

- [ ] T012 [P] [US1] Add health endpoint contract test in `service-ai/tests/contract/test_health.py`
- [ ] T013 [P] [US1] Add startup config validation integration test in `service-ai/tests/integration/test_config.py`
- [ ] T014 [US1] Implement health route in `service-ai/app/api/routes/health.py`
- [ ] T015 [US1] Wire health route and config checks through `service-ai/app/main.py`
- [ ] T016 [US1] Document `uv` setup and run commands in `service-ai/README.md`

**Checkpoint**: `service-ai` runs and can be independently validated.

---

## Phase 4: User Story 2 - Multi-Agent Swarm & Handoffs (Priority: P2)

**Goal**: Implement the `openai-agents` SDK with a Triage Agent that routes requests to specialized Domain Agents (Research, Memory), all proxied through LiteLLM.

### Tests for User Story 2
- [ ] T017 [P] [US2] Add integration test for Triage Agent routing logic in `service-ai/tests/integration/test_triage_routing.py`
- [ ] T018 [P] [US2] Add integration test for LiteLLM provider proxying in `service-ai/tests/integration/test_litellm_proxy.py`
- [ ] T019 [P] [US2] Add integration test for Memory Agent `mem0` operations in `service-ai/tests/integration/test_memory_agent.py`

### Implementation for User Story 2
- [ ] T020 [P] [US2] Define agent state and chat request schemas in `service-ai/app/schemas/chat.py`
- [ ] T021 [US2] Implement LiteLLM routing configuration for OpenAI-to-Gemini mapping in `service-ai/app/core/llm_proxy.py`
- [ ] T022 [US2] Implement `ResearchAgent` (mock web search tools) and `MemoryAgent` (mem0 tools) in `service-ai/app/agents/domain_agents.py`
- [ ] T023 [US2] Implement `TriageAgent` with handoff logic to domain agents in `service-ai/app/agents/triage_agent.py`
- [ ] T024 [US2] Implement OpenAI-compatible chat completion endpoint connecting to the Triage Agent in `service-ai/app/api/routes/chat.py`

**Checkpoint**: Multi-agent handoffs and local memory behavior works independently.

---

## Phase 5: User Story 3 - Media Agent & Async Streaming UX (Priority: P3)

**Goal**: Ensure the Media Agent triggers non-blocking background tasks and streams results via WebSocket so the user can continue chatting.

### Tests for User Story 3
- [ ] T025 [P] [US3] Add contract test for async media dispatch in `service-ai/tests/contract/test_media_dispatch.py`
- [ ] T026 [P] [US3] Add integration test for Background Worker lifecycle in `service-ai/tests/integration/test_background_worker.py`
- [ ] T027 [P] [US3] Add integration test for WebSocket background update events in `service-ai/tests/integration/test_websocket_updates.py`

### Implementation for User Story 3
- [ ] T028 [P] [US3] Define media task and streaming event schemas in `service-ai/app/schemas/streaming.py`
- [ ] T029 [US3] Implement FastAPI background worker logic for long-running tasks in `service-ai/app/workers/media_worker.py`
- [ ] T030 [US3] Implement `MediaAgent` that triggers the background worker in `service-ai/app/agents/media_agent.py`
- [ ] T031 [US3] Update `TriageAgent` to handoff media-related intents to the `MediaAgent`
- [ ] T032 [US3] Implement WebSocket streaming endpoint for real-time tokens and task updates in `service-ai/app/api/routes/stream.py`
- [ ] T033 [US3] Wire the Background Worker to push `background_update` events to the active WebSocket session

**Checkpoint**: Async media and streaming channels are independently functional.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final hardening, docs, and contract alignment for API-first delivery.

- [ ] T034 [P] Sync implemented endpoints and schemas with `specs/001-service-ai-api-first/contracts/service-ai-openapi.yaml`
- [ ] T035 [P] Add boundary impact statement for `service-ai`-only scope in `specs/001-service-ai-api-first/quickstart.md`
- [ ] T036 Run full `service-ai` test suite with `uv run pytest` and document results
- [ ] T037 Validate no `requirements.txt` exists or is modified in `service-ai/` and document `uv` compliance in `service-ai/README.md`