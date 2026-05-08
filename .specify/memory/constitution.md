# Multipurpose AI Chatbot Interface Constitution

This Constitution defines the mandatory engineering and architectural standards for the **Agentic AI Chatbot Interface** monorepo.

## Core Principles

### I. Strict MERN-Centric Microservices Architecture

To comply with strict academic and deployment requirements, the monorepo SHALL maintain three isolated execution environments:

- **`frontend`**: React/Vite application. Handles presentation and user interaction only (View).
- **`gateway-node`**: Node.js/Express API Gateway. Handles orchestration, authentication, routing, and is the core backend (Controller/Auth/DB).
- **`service-ai`**: Python FastAPI microservice. Handles LLM execution, agentic reasoning, and tool orchestration.

### II. Absolute Database Separation

MongoDB ownership is exclusively assigned to `gateway-node`.

The `service-ai` service MUST NEVER establish direct MongoDB connectivity or execute MongoDB queries. The AI service SHALL use **mem0** as its sole memory substrate for local, dynamic agentic memory operations.

Durable message history remains the gateway's responsibility.

### III. Asynchronous Non-Blocking UX

Long-running AI tool operations (for example, image generation) MUST execute via FastAPI Background Tasks.

The architecture SHALL preserve uninterrupted responsiveness for continuous text chat in the React client and request handling in the Node.js gateway. No synchronous blocking path may delay conversational throughput.

### IV. Real-Time Data Flow

All user-facing AI output MUST be delivered through streaming-first channels.

Token-level language model responses and deferred background task completions SHALL be transmitted to the frontend via WebSockets or Server-Sent Events (SSE).

### V. Rigid Type Safety and Modern Dependency Management

**Python Dependencies**: The `service-ai` environment MUST use `uv` for all dependency management (`uv add`, `uv run`). Do not generate or modify `requirements.txt`.

**Agent Loops**: Recursive agentic logic in Python MUST enforce strict runtime type validation. Dictionary key access SHALL occur only after explicit dictionary type checks to prevent `AttributeError` crashes.

## Additional Constraints

- Secrets and credentials MUST be environment-scoped per service using separate `.env` files.
- Every feature PR MUST include a boundary impact statement describing which of the three environments are touched.
- Compliance is mandatory. Non-compliant AI-generated code SHALL be rejected and regenerated.