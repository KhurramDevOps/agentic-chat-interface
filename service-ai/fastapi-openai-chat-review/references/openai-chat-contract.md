# OpenAI-Style Chat Contract Checklist

## Request envelope

- `messages` is required and non-empty.
- `messages` is an ordered array; preserve order when merging history or memory.
- Each message is an object with at least `role` and `content`.
- `role` is constrained, not a free string.
- `content` is validated before use. For text-only endpoints, `content: str` is acceptable. For multimodal endpoints, explicitly model the OpenAI content-part array shape.
- `model` is a string alias selected by the client or defaulted by the service.
- `stream` is a boolean for routes that share streaming and non-streaming request shapes.

## Message roles

Baseline roles: `system`, `user`, `assistant`, `tool`.

Modern OpenAI-compatible routes may also need `developer`. Treat it as optional unless the service promises parity with current OpenAI payloads or forwards messages directly to models that support developer instructions.

## FastAPI and Pydantic

- HTTP endpoints should accept Pydantic models in the route signature.
- WebSocket endpoints should parse JSON, check it is an object, then instantiate the same Pydantic request model used by HTTP chat routes.
- Prefer Pydantic v2 methods: `model_validate`, `model_dump`, `model_copy`, `field_validator`.
- Use `Field(..., min_length=1)` for non-empty message arrays.
- Use `Literal[...]` or enums for roles.
- Keep service-specific fields (`request_id`, `memory_context_id`, `tool_options`) outside the core OpenAI compatibility judgment unless they break payload acceptance.

## Red flags

- The route accepts `dict`, `Any`, or `Request` and manually pulls message fields without a model.
- Missing `messages` is silently converted into `payload.get("content")`, `payload.get("message")`, or `str(payload)`.
- Invalid roles reach the agent runner, OpenAI SDK, LiteLLM, or history service.
- Empty arrays pass validation.
- WebSocket validation behavior differs materially from HTTP validation.
- Error responses do not let clients distinguish malformed payloads from model or agent failures.

## Suggested tests

- Valid minimal payload with one user message.
- Valid multi-turn payload preserving system, user, and assistant order.
- Missing `messages` rejects.
- Empty `messages` rejects.
- Message with unsupported role rejects.
- Message with non-string `content` rejects for text-only chat.
- WebSocket malformed JSON returns a validation error event.
- WebSocket invalid message array returns a validation error event and does not call the agent runner.
