# Research: Service AI API-First Foundation

## Decision 1: Use `uv` as the exclusive Python dependency workflow

- **Decision**: Use `uv add` for dependencies and `uv run` for execution and testing in `service-ai`.
- **Rationale**: Satisfies constitution requirement for modern dependency management and avoids toolchain drift.
- **Alternatives considered**:
  - `pip` + `venv`: Rejected due to constitution non-compliance.
  - Poetry: Rejected because repository policy explicitly requires `uv`.

## Decision 2: Implement OpenAI-compatible API shape backed by LiteLLM->Gemini routing

- **Decision**: Build chat endpoint schemas aligned with OpenAI-style payloads while delegating provider translation/routing to LiteLLM configured for Gemini.
- **Rationale**: Preserves client compatibility while allowing provider switching without changing endpoint contract.
- **Alternatives considered**:
  - Native Gemini request/response format: Rejected due to reduced compatibility with OpenAI-style callers.
  - Direct provider SDK calls without routing layer: Rejected due to weaker abstraction and harder provider portability.

## Decision 3: Use mem0 as local dynamic memory substrate only

- **Decision**: Encapsulate all memory operations in a dedicated service wrapping mem0 APIs.
- **Rationale**: Enforces constitutional boundary that durable history and database ownership remain outside `service-ai`.
- **Alternatives considered**:
  - Direct MongoDB access from `service-ai`: Rejected as unconstitutional.
  - In-memory Python dict only: Rejected due to limited retrieval patterns and unstable behavior across restarts.

## Decision 4: Run long-running media operations via FastAPI background tasks

- **Decision**: Use FastAPI background task execution for deferred media generation operations.
- **Rationale**: Maintains non-blocking request handling and conversational throughput.
- **Alternatives considered**:
  - Synchronous in-request media generation: Rejected for latency and throughput impact.
  - External queue system in this phase: Deferred to later scaling phase; unnecessary for initial service-only iteration.

## Decision 5: Provide streaming output via SSE and WebSocket routes

- **Decision**: Implement SSE as baseline stream transport and WebSocket endpoint for bi-directional/real-time session support.
- **Rationale**: Meets streaming-first constitution requirement and enables flexible client integration patterns.
- **Alternatives considered**:
  - Polling-only updates: Rejected by constitution.
  - WebSocket-only approach: Not chosen as sole option to keep simpler HTTP streaming compatibility via SSE.

## Decision 6: Enforce runtime type guards in recursive agent loops

- **Decision**: Add explicit runtime payload checks before nested access in agent/tool loops and parser code paths.
- **Rationale**: Prevents common `AttributeError` failures from malformed/heterogeneous tool payloads.
- **Alternatives considered**:
  - Trust typed hints only: Rejected because runtime data can violate static assumptions.
  - Broad `try/except` without type guards: Rejected due to poor diagnosability and hidden errors.
