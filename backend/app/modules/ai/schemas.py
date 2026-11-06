"""Request and response schemas for the /ai API. Inputs are validated here (rule 4)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Hard ceiling at the schema edge. The configurable LLM_MAX_INPUT_CHARS is enforced in the service.
_CONTENT_HARD_CAP = 100_000
_TITLE_MAX = 200


# ── conversations ────────────────────────────────────────────────────────────


class ConversationOut(BaseModel):
    id: uuid.UUID
    title: str | None
    status: Literal["active", "archived"]
    model_id: str | None
    last_message_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConversationResponse(BaseModel):
    success: bool = True
    data: ConversationOut


class ConversationListResponse(BaseModel):
    success: bool = True
    data: list[ConversationOut]
    total: int
    limit: int
    offset: int


class CreateConversationRequest(BaseModel):
    title: str | None = Field(default=None, max_length=_TITLE_MAX)
    model_id: str | None = Field(default=None, max_length=128)

    @field_validator("title")
    @classmethod
    def strip_title(cls, v: str | None) -> str | None:
        v = v.strip() if v is not None else v
        return v or None


class UpdateConversationRequest(BaseModel):
    title: str = Field(min_length=1, max_length=_TITLE_MAX)

    @field_validator("title")
    @classmethod
    def strip_title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Title cannot be blank.")
        return v


# ── messages ─────────────────────────────────────────────────────────────────


class MessageOut(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    status: Literal["pending", "streaming", "completed", "failed", "cancelled"]
    sequence_number: int
    model_id: str | None
    prompt_key: str | None
    prompt_version: int | None
    input_tokens: int | None
    output_tokens: int | None
    usage_source: str | None
    finish_reason: str | None
    error_code: str | None
    regenerates_message_id: uuid.UUID | None
    superseded_at: datetime | None
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class MessageListResponse(BaseModel):
    success: bool = True
    data: list[MessageOut]
    total: int
    limit: int
    offset: int


class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=_CONTENT_HARD_CAP)
    model_id: str | None = Field(default=None, max_length=128)
    stream: bool = False

    @field_validator("content")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Message cannot be blank.")
        return v


class UsageOut(BaseModel):
    input_tokens: int | None
    output_tokens: int | None
    reasoning_tokens: int | None
    source: str


class SendMessageData(BaseModel):
    conversation_id: uuid.UUID
    user_message: MessageOut
    message: MessageOut
    usage: UsageOut


class SendMessageResponse(BaseModel):
    success: bool = True
    data: SendMessageData


class FeedbackRequest(BaseModel):
    rating: Literal["positive", "negative"]
    feedback_text: str | None = Field(default=None, max_length=1000)


class FeedbackOut(BaseModel):
    message_id: uuid.UUID
    rating: Literal["positive", "negative"]
    feedback_text: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class FeedbackResponse(BaseModel):
    success: bool = True
    data: FeedbackOut


# ── models ───────────────────────────────────────────────────────────────────


class CapabilitiesOut(BaseModel):
    streaming: bool
    structured_output: bool
    usage_reporting: bool
    system_prompt: bool
    tool_calling: bool
    count_tokens: bool
    thinking_budget: bool


class ModelOut(BaseModel):
    id: str
    display_name: str
    is_default: bool
    capabilities: CapabilitiesOut
    max_input_tokens: int | None
    max_output_tokens: int | None
    is_test_provider: bool


class ModelListResponse(BaseModel):
    success: bool = True
    data: list[ModelOut]


class ModelResponse(BaseModel):
    success: bool = True
    data: ModelOut


class CapabilitiesResponse(BaseModel):
    success: bool = True
    data: CapabilitiesOut
