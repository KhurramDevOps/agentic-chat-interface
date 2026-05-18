---
name: fastapi-openai-chat-review
description: Review FastAPI Python services that expose OpenAI-compatible chatbot endpoints. Use when checking chat completions, streaming, SSE, or WebSocket routes for standard OpenAI-style payloads, messages arrays, role/content structure, request/response envelopes, and Pydantic validation in FastAPI route signatures or manually parsed JSON payloads.
---

# FastAPI OpenAI Chat Review

## Overview

Use this skill to review FastAPI chatbot APIs for compatibility with OpenAI-style chat payloads and predictable Pydantic validation. Focus on request contracts, message arrays, route boundaries, response envelopes, and tests that prove invalid payloads fail before they reach agent or model code.

## Quick Start

1. Inspect the service shape:
   - `app/api/routes/`
   - `app/schemas/`
   - `tests/contract/`
   - `tests/integration/`
2. Run the static scanner from the service root when available:

```bash
python fastapi-openai-chat-review/scripts/review_fastapi_openai_chat.py .
```

3. Read `references/openai-chat-contract.md` when the endpoint contract or failure mode is unclear.
4. Report findings first, with file and line references, then summarize validation coverage and suggested tests.

## Review Workflow

Check the inbound schema before the route code. Confirm that the main chat request model has a `messages` field typed as a non-empty list of message objects, not raw dictionaries, and that each message validates `role` and `content`.

Check route signatures next. Prefer FastAPI endpoints that accept a Pydantic request model directly, such as `body: ChatRequest`, so malformed JSON receives a `422` response automatically. For WebSockets or other manual JSON paths, require explicit parsing into the same Pydantic models and a clear validation error event.

Check downstream calls after validation. Agent, swarm, LiteLLM, OpenAI SDK, and history code should receive normalized message objects or OpenAI-compatible dictionaries derived from validated models. Avoid letting unchecked `dict`, fallback `"message"` strings, or arbitrary payload text become model input unless the route is intentionally compatibility-shimmed and tests cover it.

Check tests last. Contract tests should cover valid chat requests, missing `messages`, empty `messages`, invalid roles, non-string content, malformed WebSocket JSON, and streaming routes using the same request schema as non-streaming routes.

## Contract Expectations

Treat this as the baseline for OpenAI-style chat routes:

```json
{
  "model": "provider/model-or-alias",
  "messages": [
    {"role": "system", "content": "optional instructions"},
    {"role": "user", "content": "hello"}
  ],
  "stream": false
}
```

For this repository's `service-ai` shape, `request_id` and `memory_context_id` may be service-specific fields. Review them as local envelope fields, not OpenAI compatibility fields.

Accepted message roles normally include `system`, `user`, `assistant`, and `tool`. Flag missing `developer` only when the endpoint claims modern OpenAI parity or forwards payloads directly to OpenAI models that expect it.

## Pydantic Checks

Prefer Pydantic v2 patterns:

```python
from typing import Literal
from pydantic import BaseModel, Field

class ChatMessage(BaseModel):
    role: Literal["system", "developer", "user", "assistant", "tool"]
    content: str

class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(..., min_length=1)
    model: str
    stream: bool = False
```

Look for these issues:

- `messages: list[dict]`, `dict[str, Any]`, or `Any` at the API boundary.
- Manual `payload.get("messages", [])` without Pydantic validation.
- Empty-message fallbacks that convert arbitrary payloads to user messages.
- Validators that duplicate `Field(min_length=1)` without adding behavior.
- Route code that catches broad exceptions and hides validation details from clients.
- Response models omitted from HTTP endpoints that return chatbot output.

## Reporting

Use a code-review style response:

- Lead with bugs, compatibility risks, or missing validation.
- Include exact file and line references.
- Separate "must fix" endpoint contract issues from "consider" OpenAI parity choices.
- Mention scanner results if the script was run.
- Propose focused contract tests for every changed or risky route.

Do not rewrite endpoint behavior unless the user asks for fixes. If asked to fix, keep changes small and aligned with the existing schema and route patterns.
