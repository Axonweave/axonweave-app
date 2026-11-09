"""Request and response schemas for the /ai API. Inputs are validated here (rule 4)."""

import uuid
from datetime import datetime
from decimal import Decimal
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
    scope_type: str
    scope_id: uuid.UUID | None
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


ScopeKindLiteral = Literal["workspace", "subject", "folder", "chapter", "document"]


class ConversationScopeIn(BaseModel):
    kind: ScopeKindLiteral
    id: uuid.UUID


class CreateConversationRequest(BaseModel):
    title: str | None = Field(default=None, max_length=_TITLE_MAX)
    model_id: str | None = Field(default=None, max_length=128)
    # Validated against the caller's own data in the service; omitted = general chat.
    scope: ConversationScopeIn | None = None

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
    answer_mode: str | None
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
    # Only meaningful for a conversation with a document scope; ignored for general chat.
    answer_mode: Literal["document_only", "document_first", "general"] | None = None

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


class CitationOut(BaseModel):
    id: uuid.UUID
    message_id: uuid.UUID
    rank: int
    chunk_id: uuid.UUID | None = None
    document_id: uuid.UUID | None
    document_name: str
    page_number: int | None
    slide_number: int | None
    section_heading: str | None
    snippet: str | None
    available: bool

    model_config = {"from_attributes": True}


class CitationResponse(BaseModel):
    success: bool = True
    data: CitationOut


class CitationListResponse(BaseModel):
    success: bool = True
    data: list[CitationOut]


class SendMessageData(BaseModel):
    conversation_id: uuid.UUID
    user_message: MessageOut
    message: MessageOut
    usage: UsageOut
    citations: list[CitationOut] = []


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


class AiStatusOut(BaseModel):
    """What the UI needs to know before any model call. Never exposes keys or settings."""

    configured: bool
    provider_display_name: str | None
    is_test_provider: bool
    max_input_chars: int


class AiStatusResponse(BaseModel):
    success: bool = True
    data: AiStatusOut


class ModelListResponse(BaseModel):
    success: bool = True
    data: list[ModelOut]


class ModelResponse(BaseModel):
    success: bool = True
    data: ModelOut


class CapabilitiesResponse(BaseModel):
    success: bool = True
    data: CapabilitiesOut


# ── regenerate / cancel ──────────────────────────────────────────────────────


class RegenerateRequest(BaseModel):
    model_id: str | None = Field(default=None, max_length=128)
    stream: bool = False


class MessageResponse(BaseModel):
    success: bool = True
    data: MessageOut


# ── usage ────────────────────────────────────────────────────────────────────


class CostByCurrency(BaseModel):
    currency: str
    amount: Decimal


class UsageRecordOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    conversation_id: uuid.UUID | None
    message_id: uuid.UUID | None
    model_id: str
    model_display_name: str
    request_status: Literal["success", "failed", "cancelled"]
    error_code: str | None
    input_tokens: int | None
    output_tokens: int | None
    reasoning_tokens: int | None
    total_tokens: int | None
    usage_source: str | None
    estimated_cost: Decimal | None
    currency: str | None
    pricing_version: str | None
    duration_ms: int | None


class UsageListResponse(BaseModel):
    success: bool = True
    data: list[UsageRecordOut]
    total: int
    limit: int
    offset: int


class UsageTotals(BaseModel):
    requests: int
    failed_requests: int
    cancelled_requests: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    # Unknown is not zero: how many requests actually had token counts / a cost estimate.
    token_known_requests: int
    cost_known_requests: int
    cost_by_currency: list[CostByCurrency]


class UsageSummaryOut(UsageTotals):
    days: int
    since: datetime


class UsageSummaryResponse(BaseModel):
    success: bool = True
    data: UsageSummaryOut


class UsageByModelOut(UsageTotals):
    model_id: str
    display_name: str


class UsageByModelResponse(BaseModel):
    success: bool = True
    days: int
    data: list[UsageByModelOut]
