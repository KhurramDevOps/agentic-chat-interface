"""
app/api/routes/chat.py  (T024)
────────────────────────────────
OpenAI-compatible chat completion endpoint.

Routes:
  POST /api/v1/chat/completions — non-streaming chat via TriageAgent swarm

History flow:
  1. Derive session_id from memory_context_id (or request_id fallback).
  2. Load existing history from MongoDB via get_history().
  3. Merge history + new user message into request.messages.
  4. Run swarm with full context.
  5. Append user message + assistant response via append_to_history().

Constitution compliance:
  - Delegates all LLM work to the swarm; route is thin orchestration only.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.agents.swarm import run_swarm
from app.api.deps import get_request_id, http_error, verify_api_key
from app.core.logging import get_logger
from app.schemas.chat import AgentResponse, ChatMessage, ChatRequest
from app.services.history_service import append_to_history, get_history

logger = get_logger(__name__)
router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.post(
    "/completions",
    response_model=AgentResponse,
    status_code=status.HTTP_200_OK,
    summary="Chat completion via TriageAgent swarm",
    tags=["Chat"],
    dependencies=[Depends(verify_api_key)],
)
@limiter.limit("10/minute")
async def chat_completions(
    request: Request,
    body: ChatRequest,
    request_id: str = Depends(get_request_id),
) -> AgentResponse:
    if body.request_id == "":
        body = body.model_copy(update={"request_id": request_id})

    session_id = body.memory_context_id or body.request_id

    logger.info(
        "POST /chat/completions — request_id=%s, session_id=%s, model=%s",
        body.request_id, session_id, body.model,
    )

    # ── Load history and merge ────────────────────────────────────────────
    history = await get_history(session_id)

    if history:
        stored_messages = [ChatMessage(role=m["role"], content=m["content"]) for m in history]
        incoming_contents = {m.content for m in body.messages}
        deduped_history = [m for m in stored_messages if m.content not in incoming_contents]
        merged_messages = deduped_history + list(body.messages)
        body = body.model_copy(update={"messages": merged_messages})
        logger.info(
            "history loaded — session=%s, history_msgs=%d, total_msgs=%d",
            session_id, len(history), len(merged_messages),
        )

    # ── Run swarm ─────────────────────────────────────────────────────────
    try:
        response = await run_swarm(body)
    except Exception as exc:
        logger.exception("Swarm execution failed — request_id=%s", body.request_id)
        raise http_error(
            status_code=status.HTTP_502_BAD_GATEWAY,
            code="SWARM_ERROR",
            message=f"Agent swarm encountered an error: {exc}",
            request_id=body.request_id,
        ) from exc

    # ── Persist to MongoDB ────────────────────────────────────────────────
    await append_to_history(session_id, "user", body.last_user_message)
    await append_to_history(session_id, "assistant", response.content)

    logger.info("history saved — session=%s", session_id)

    return response
