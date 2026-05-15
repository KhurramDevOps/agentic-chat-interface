"""
app/api/routes/sse.py
──────────────────────
Server-Sent Events (SSE) streaming endpoint.

Endpoint:
  POST /api/v1/chat/stream

Alternative to WebSocket for clients that prefer SSE (browsers, curl).
Accepts the same JSON payload as /chat/completions and streams tokens
as text/event-stream events.

Event format:
  data: {"type": "token", "content": "Hello"}
  data: {"type": "complete"}
  data: {"type": "error", "content": "..."}
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import StreamingResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.agents.swarm import stream_swarm
from app.api.deps import get_request_id, verify_api_key
from app.core.logging import get_logger
from app.schemas.chat import ChatMessage, ChatRequest
from app.services.history_service import append_to_history, get_history

logger = get_logger(__name__)
router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.post(
    "/stream",
    summary="SSE streaming chat via TriageAgent swarm",
    tags=["Chat"],
    dependencies=[Depends(verify_api_key)],
)
@limiter.limit("10/minute")
async def sse_chat(
    request: Request,
    body: ChatRequest,
    request_id: str = Depends(get_request_id),
) -> StreamingResponse:
    """
    Stream LLM tokens as Server-Sent Events.
    Each token arrives as: data: {"type": "token", "content": "..."}
    Terminated by:         data: {"type": "complete"}
    """
    if body.request_id == "":
        body = body.model_copy(update={"request_id": request_id})

    session_id = body.memory_context_id or body.request_id

    # Load and merge history
    history = await get_history(session_id)
    if history:
        stored = [ChatMessage(role=m["role"], content=m["content"]) for m in history]
        incoming = {m.content for m in body.messages}
        deduped = [m for m in stored if m.content not in incoming]
        body = body.model_copy(update={"messages": deduped + list(body.messages)})

    async def event_generator():
        full_response = ""
        try:
            async for delta in stream_swarm(body):
                if delta:
                    full_response += delta
                    payload = json.dumps({"type": "token", "content": delta})
                    yield f"data: {payload}\n\n"
        except Exception as exc:
            logger.exception("SSE stream error — request_id=%s", body.request_id)
            payload = json.dumps({"type": "error", "content": str(exc)})
            yield f"data: {payload}\n\n"
            return

        yield f"data: {json.dumps({'type': 'complete'})}\n\n"

        # Save to history
        await append_to_history(session_id, "user", body.last_user_message)
        if full_response:
            await append_to_history(session_id, "assistant", full_response)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
