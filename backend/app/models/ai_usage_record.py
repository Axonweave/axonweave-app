import uuid
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Numeric, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.database.fk import SetNullColumnsFK


class AiUsageRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One row per provider call. Survives deletion of its conversation/message (D-53): only the
    nullable link column is cleared, so usage and cost history stay. Unknown values are NULL."""

    __tablename__ = "ai_usage_records"
    __table_args__ = (
        SetNullColumnsFK(
            ["conversation_id", "user_id"],
            ["conversations.id", "conversations.user_id"],
            set_null=["conversation_id"],
            name="fk_ai_usage_conversation_owner",
        ),
        SetNullColumnsFK(
            ["message_id", "user_id"],
            ["messages.id", "messages.user_id"],
            set_null=["message_id"],
            name="fk_ai_usage_message_owner",
        ),
        CheckConstraint(
            "usage_source IS NULL OR "
            "usage_source IN ('provider_reported', 'estimated', 'unavailable')",
            name="ck_ai_usage_source",
        ),
        CheckConstraint(
            "request_kind IN ('chat', 'embedding', 'generation')", name="ck_ai_usage_request_kind"
        ),
        CheckConstraint(
            "request_status IN ('success', 'failed', 'cancelled')", name="ck_ai_usage_status"
        ),
        CheckConstraint(
            "(input_tokens IS NULL OR input_tokens >= 0) AND "
            "(output_tokens IS NULL OR output_tokens >= 0) AND "
            "(reasoning_tokens IS NULL OR reasoning_tokens >= 0) AND "
            "(estimated_cost IS NULL OR estimated_cost >= 0)",
            name="ck_ai_usage_non_negative",
        ),
        Index("ix_ai_usage_user_created", "user_id", "created_at"),
        Index("ix_ai_usage_model_created", "model_id", "created_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("llm_providers.id", ondelete="RESTRICT"), nullable=False
    )
    model_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("llm_models.id", ondelete="RESTRICT"), nullable=False
    )
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reasoning_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    usage_source: Mapped[str | None] = mapped_column(String(24), nullable=True)
    estimated_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 8), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    pricing_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    request_kind: Mapped[str] = mapped_column(
        String(16), nullable=False, default="chat", server_default=text("'chat'")
    )
    request_status: Mapped[str] = mapped_column(String(16), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider_request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
