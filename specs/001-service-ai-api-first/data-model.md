# Data Model: Service AI API-First Foundation

## 1. Agentic Entities (The Swarm)

### TriageAgent (Router)
- **Description:** The primary entry point. Evaluates user intent, maintains conversational state, handles casual chat, and routes complex requests to Domain Agents.
- **Capabilities:** Intent classification, standard OpenAI chat formatting, sub-agent handoff.

### ResearchAgent (Domain)
- **Description:** Specialized sub-agent for knowledge gathering.
- **Tools:** Web Search API (e.g., DuckDuckGo/Brave MCP), Deep Research scraping.

### MemoryAgent (Domain)
- **Description:** Specialized sub-agent for contextual recall.
- **Tools:** `mem0` read/write operations to manage user preferences and long-term context.

### MediaAgent (Domain)
- **Description:** Specialized sub-agent for deferred media generation.
- **Tools:** Image generation trigger, Video generation trigger.
- **Constraint:** MUST dispatch tasks to the FastAPI Background Worker and immediately return an acknowledgment token to the Triage Agent.

## 2. Core Data Structures

### Entity: ChatRequestEnvelope
- **Description**: OpenAI-style inbound chat request accepted by `service-ai`.
- **Fields**:
  - `request_id` (string, required)
  - `messages` (array, required)
  - `model` (string, required; OpenAI-style alias for LiteLLM routing)
  - `stream` (boolean, optional; default false)
  - `memory_context_id` (string, optional)
  - `tool_options` (object, optional)
- **Validation Rules**:
  - `messages` must be non-empty.
  - `model` must map to a configured LiteLLM provider target.
  - if `stream=true`, response mode must emit incremental events.

### Entity: ChatStreamEvent
- **Description**: Outbound incremental event payload for SSE/WebSocket streaming.
- **Fields**:
  - `event_type` (enum: token|status|error|complete|background_update)
  - `request_id` (string, required)
  - `sequence` (integer, required)
  - `delta` (string, optional)
  - `metadata` (object, optional)
  - `timestamp` (datetime string, required)
- **Validation Rules**:
  - `sequence` must be monotonic per request.
  - `event_type=complete` must terminate the stream.
  - `event_type=background_update` must carry async task status changes.

### Entity: MemoryRecord
- **Description**: Local mem0 memory unit used by agentic flows.
- **Fields**:
  - `memory_id` (string, required)
  - `context_id` (string, required)
  - `content` (string, required)
  - `tags` (array[string], optional)
  - `created_at` (datetime string, required)
  - `updated_at` (datetime string, optional)
- **Validation Rules**:
  - `context_id` required for retrieval grouping.
  - content cannot be empty.

### Entity: BackgroundMediaTask
- **Description**: Task record for deferred media generation jobs.
- **Fields**:
  - `task_id` (string, required)
  - `request_id` (string, required)
  - `job_type` (enum: image|video|audio)
  - `status` (enum: queued|running|completed|failed)
  - `input_payload` (object, required)
  - `result_payload` (object, optional)
  - `error_message` (string, optional)
  - `created_at` (datetime string, required)
  - `updated_at` (datetime string, required)
- **Validation Rules**:
  - State transitions must follow: `queued -> running -> completed|failed`.
  - `result_payload` required when `status=completed`.
  - `error_message` required when `status=failed`.