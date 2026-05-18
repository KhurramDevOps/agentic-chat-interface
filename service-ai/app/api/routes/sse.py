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

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import StreamingResponse
from slowapi import Limiter

from app.agents.swarm import get_stream_usage, stream_swarm
from app.api.deps import CurrentUser, get_request_id, verify_api_key, get_user_key
from app.core.config import get_settings
from app.core.logging import get_logger
from app.schemas.chat import ChatMessage, ChatRequest
from app.services import history_service, memory_service
from app.services.user_service import get_or_create_user, record_token_usage

logger = get_logger(__name__)
router = APIRouter()
limiter = Limiter(key_func=get_user_key)


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
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    request_id: str = Depends(get_request_id),
) -> StreamingResponse:
    """
    Stream LLM tokens as Server-Sent Events.
    Each token arrives as: data: {"type": "token", "content": "..."}
    Terminated by:         data: {"type": "complete"}
    """
    if body.request_id == "":
        body = body.model_copy(update={"request_id": request_id})

    settings = get_settings()
    normalized_messages = body.normalized_messages()
    user_message = body.get_user_message()
    if not normalized_messages or not user_message:
        from app.api.deps import http_error  # noqa: PLC0415
        from fastapi import status  # noqa: PLC0415
        raise http_error(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="VALIDATION_ERROR",
            message="messages or message must include at least one user message.",
            request_id=body.request_id,
        )

    session_id = body.session_id or body.memory_context_id or body.request_id
    user_id = user["user_id"]
    body = body.model_copy(update={
        "messages": normalized_messages,
        "memory_context_id": session_id,
        "model": body.model or settings.active_model,
    })

    # Resolve / create user identity
    await get_or_create_user(session_id=session_id, user_id=user_id)

    # Load and merge history
    history = await history_service.get_history(session_id=session_id, user_id=user_id)
    if history:
        stored = [ChatMessage(role=m["role"], content=m["content"]) for m in history]
        incoming = {m.text_content for m in body.normalized_messages()}
        deduped = [m for m in stored if m.text_content not in incoming]
        body = body.model_copy(update={"messages": deduped + body.normalized_messages()})

    memory_context = await memory_service.get_memory_context_for_user(user_id=user_id)
    if memory_context:
        body = body.model_copy(
            update={"messages": [ChatMessage(role="system", content=memory_context)] + body.normalized_messages()}
        )

    await history_service.save_message(
        session_id=session_id,
        user_id=user_id,
        role="user",
        content=user_message,
    )

    async def event_generator():
        full_response = ""
        result_container: dict = {}
        try:
            async for delta in stream_swarm(body, result_container=result_container):
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

        if full_response:
            await history_service.save_message(
                session_id=session_id,
                user_id=user_id,
                role="assistant",
                content=full_response,
            )

        usage = get_stream_usage(result_container.get("result"))
        await record_token_usage(
            session_id=session_id,
            prompt_tokens=usage["prompt_tokens"],
            completion_tokens=usage["completion_tokens"],
            user_id=user_id,
        )
        background_tasks.add_task(
            memory_service.extract_memories_background,
            messages=[
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": full_response},
            ],
            user_id=user_id,
            session_id=session_id,
        )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
