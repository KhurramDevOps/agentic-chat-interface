"""
app/api/routes/users.py
────────────────────────
User management endpoints.

Routes:
  GET    /api/v1/users/{user_id}/usage       — token usage stats for a user
  DELETE /api/v1/chat/history/{session_id}   — clear conversation history
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.deps import verify_api_key
from app.core.logging import get_logger
from app.services.history_service import clear_history
from app.services.user_service import get_or_create_user

logger = get_logger(__name__)
router = APIRouter()


class UsageResponse(BaseModel):
    user_id: str
    total_tokens_used: int
    prompt_tokens: int
    completion_tokens: int
    is_anonymous: bool


@router.get(
    "/{user_id}/usage",
    response_model=UsageResponse,
    status_code=status.HTTP_200_OK,
    summary="Get token usage for a user",
    tags=["Users"],
    dependencies=[Depends(verify_api_key)],
)
async def get_user_usage(user_id: str) -> UsageResponse:
    """Return cumulative token usage counters for the given user_id."""
    doc = await get_or_create_user(session_id=user_id, user_id=user_id)
    return UsageResponse(
        user_id=doc["user_id"],
        total_tokens_used=doc.get("total_tokens_used", 0),
        prompt_tokens=doc.get("prompt_tokens", 0),
        completion_tokens=doc.get("completion_tokens", 0),
        is_anonymous=doc.get("is_anonymous", True),
    )


history_router = APIRouter()


@history_router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Clear conversation history for a session",
    tags=["Chat"],
    dependencies=[Depends(verify_api_key)],
)
async def delete_history(session_id: str) -> None:
    """Delete all stored messages for the given session_id."""
    await clear_history(session_id)
    logger.info("History cleared — session_id=%s", session_id)
