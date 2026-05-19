"""
app/schemas/chat.py  (T020)
────────────────────────────
Pydantic models for the chat API layer.

Covers:
  - ChatRequest   : inbound OpenAI-style request envelope
  - AgentMetadata : which agent handled the request and why
  - AgentResponse : outbound response wrapping the agent's final output
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


# ── Inbound ───────────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str


class ChatRequest(BaseModel):
    """
    OpenAI-style chat request accepted by the /chat endpoint.
    Maps to ChatRequestEnvelope in the data model spec.
    """

    request_id: str = Field(..., description="Client-supplied idempotency key.")
    messages: list[ChatMessage] = Field(..., min_length=1)
    model: str = Field(
        default="groq/llama-3.3-70b-versatile",
        description="OpenAI-style model alias resolved by LiteLLM.",
    )
    stream: bool = Field(default=False)
    memory_context_id: str | None = Field(
        default=None,
        description="mem0 context bucket for this conversation.",
    )
    tool_options: dict[str, Any] | None = None

    @field_validator("messages")
    @classmethod
    def messages_not_empty(cls, v: list[ChatMessage]) -> list[ChatMessage]:
        if not v:
            raise ValueError("messages must contain at least one entry.")
        return v

    @property
    def last_user_message(self) -> str:
        """Return the content of the most recent user turn."""
        for msg in reversed(self.messages):
            if msg.role == "user":
                return msg.content
        return ""


# ── Outbound ──────────────────────────────────────────────────────────────────

class AgentMetadata(BaseModel):
    """Describes which agent produced the final response."""

    agent_name: str
    handoff_occurred: bool = False
    handoff_chain: list[str] = Field(default_factory=list)
    turns_used: int = 0


class AgentResponse(BaseModel):
    """
    Outbound response envelope returned by the /chat endpoint.
    Wraps the agent's final_output with routing metadata.
    """

    request_id: str
    content: str
    agent: AgentMetadata
    model: str
    usage: dict[str, int] | None = None
