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

import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ── Inbound ───────────────────────────────────────────────────────────────────

class MessageContent(BaseModel):
    type: str
    text: str | None = None
    image_url: dict[str, Any] | None = None


ChatContent = str | list[MessageContent | dict[str, Any]]


class ChatMessage(BaseModel):
    role: Literal["system", "developer", "user", "assistant", "tool"]
    content: ChatContent

    @property
    def text_content(self) -> str:
        if isinstance(self.content, str):
            return self.content
        parts: list[str] = []
        for part in self.content:
            if isinstance(part, MessageContent):
                if part.type == "text" and part.text:
                    parts.append(part.text)
            elif isinstance(part, dict) and part.get("type") == "text":
                text = part.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return " ".join(parts).strip()


class ChatRequest(BaseModel):
    """
    OpenAI-style chat request accepted by the /chat endpoint.
    Maps to ChatRequestEnvelope in the data model spec.
    """

    model_config = ConfigDict(extra="ignore")

    model: str | None = Field(
        default=None,
        description="OpenAI-style model alias resolved by LiteLLM.",
    )
    messages: list[ChatMessage] | None = Field(default=None)
    message: str | None = Field(default=None, description="Single-message shorthand.")
    session_id: str | None = Field(default=None)
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    stream: bool = Field(default=False)
    memory_context_id: str | None = Field(
        default=None,
        description="mem0 context bucket for this conversation.",
    )
    tool_options: dict[str, Any] | None = None

    @field_validator("messages")
    @classmethod
    def messages_not_empty(cls, v: list[ChatMessage] | None) -> list[ChatMessage] | None:
        if v is not None and not v:
            raise ValueError("messages must contain at least one entry when provided.")
        return v

    def normalized_messages(self) -> list[ChatMessage]:
        if self.messages:
            return self.messages
        if self.message:
            return [ChatMessage(role="user", content=self.message)]
        return []

    def get_user_message(self) -> str:
        """Extract user message from either simple or OpenAI-style input."""
        if self.message:
            return self.message
        for msg in reversed(self.normalized_messages()):
            if msg.role == "user":
                return msg.text_content
        return ""

    @property
    def last_user_message(self) -> str:
        """Return the content of the most recent user turn."""
        return self.get_user_message()


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
