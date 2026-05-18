"""
app/api/routes/chat.py  (T024)
────────────────────────────────
OpenAI-compatible chat completion endpoint.

Routes:
  POST /api/v1/chat/completions — non-streaming chat via TriageAgent swarm

History flow:
  1. Derive session_id from memory_context_id (or request_id fallback).
  2. Resolve / create user identity via user_service.
  3. Load existing history from MongoDB via get_history().
  4. Merge history + new user message into request.messages.
  5. Run swarm with full context.
  6. Append user message + assistant response via append_to_history().
  7. Record token usage against the user profile.

Constitution compliance:
  - Delegates all LLM work to the swarm; route is thin orchestration only.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Request, status
from slowapi import Limiter

from app.agents.swarm import run_swarm
from app.api.deps import CurrentUser, get_request_id, http_error, verify_api_key, get_user_key
from app.core.config import get_settings
from app.core.logging import get_logger
from app.schemas.chat import AgentResponse, ChatMessage, ChatRequest
from app.services import history_service, memory_service
from app.services.user_service import get_or_create_user, record_token_usage

logger = get_logger(__name__)
router = APIRouter()
limiter = Limiter(key_func=get_user_key)


@router.post(
    "/completions",
    response_model=AgentResponse,
    status_code=status.HTTP_200_OK,
    summary="Chat completion via TriageAgent swarm",
    tags=["Chat"],
    dependencies=[Depends(verify_api_key)],
)
@limiter.limit("20/minute")
async def chat_completions(
    request: Request,
    body: ChatRequest,
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    request_id: str = Depends(get_request_id),
) -> AgentResponse:
    if body.request_id == "":
        body = body.model_copy(update={"request_id": request_id})

    settings = get_settings()
    normalized_messages = body.normalized_messages()
    user_message = body.get_user_message()
    if not normalized_messages or not user_message:
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

    logger.info(
        "POST /chat/completions — request_id=%s, session_id=%s, model=%s",
        body.request_id, session_id, body.model,
    )

    # ── Resolve user identity ─────────────────────────────────────────────
    await get_or_create_user(session_id=session_id, user_id=user_id)

    # ── Load history and merge ────────────────────────────────────────────
    history = await history_service.get_history(session_id=session_id, user_id=user_id)

    if history:
        stored_messages = [ChatMessage(role=m["role"], content=m["content"]) for m in history]
        incoming_contents = {m.text_content for m in body.normalized_messages()}
        deduped_history = [m for m in stored_messages if m.text_content not in incoming_contents]
        merged_messages = deduped_history + body.normalized_messages()
        body = body.model_copy(update={"messages": merged_messages})
        logger.info(
            "history loaded — session=%s, history_msgs=%d, total_msgs=%d",
            session_id, len(history), len(merged_messages),
        )

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

    # ── Persist assistant response to MongoDB ─────────────────────────────
    await history_service.save_message(
        session_id=session_id,
        user_id=user_id,
        role="assistant",
        content=response.content,
    )

    # ── Record token usage ────────────────────────────────────────────────
    if response.usage:
        await record_token_usage(
            session_id=session_id,
            prompt_tokens=response.usage.get("prompt_tokens", 0),
            completion_tokens=response.usage.get("completion_tokens", 0),
            user_id=user_id,
        )

    background_tasks.add_task(
        memory_service.extract_memories_background,
        messages=[
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": response.content},
        ],
        user_id=user_id,
        session_id=session_id,
    )

    logger.info("history saved — session=%s", session_id)

    return response


@router.get(
    "/history/{session_id}",
    status_code=status.HTTP_200_OK,
    summary="Get authenticated session history",
    tags=["Chat"],
    dependencies=[Depends(verify_api_key)],
)
async def get_session_history(
    session_id: str,
    user: CurrentUser,
) -> dict:
    messages = await history_service.get_history(
        session_id=session_id,
        user_id=user["user_id"],
    )
    return {"session_id": session_id, "messages": messages, "user_id": user["user_id"]}


@router.get(
    "/sessions",
    status_code=status.HTTP_200_OK,
    summary="List authenticated user sessions",
    tags=["Chat"],
    dependencies=[Depends(verify_api_key)],
)
async def get_user_sessions(user: CurrentUser) -> dict:
    sessions = await history_service.get_sessions_for_user(user_id=user["user_id"])
    return {"sessions": sessions}
