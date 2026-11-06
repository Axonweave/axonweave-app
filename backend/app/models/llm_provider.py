import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class LLMProvider(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A configured provider adapter (gemini, fake). No credentials are stored (rule 12)."""

    __tablename__ = "llm_providers"

    provider_name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class LLMModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A model offered by a provider. `internal_id` is our stable internal id; the provider's own
    model string is `provider_model_id` (verified, never guessed: D-38)."""

    __tablename__ = "llm_models"
    __table_args__ = (
        UniqueConstraint("provider_id", "provider_model_id", name="uq_llm_models_provider_model"),
        UniqueConstraint("internal_id", name="uq_llm_models_internal_id"),
        CheckConstraint(
            "max_input_tokens IS NULL OR max_input_tokens > 0", name="ck_llm_models_max_input"
        ),
        CheckConstraint(
            "max_output_tokens IS NULL OR max_output_tokens > 0", name="ck_llm_models_max_output"
        ),
        # At most one default model.
        Index(
            "uq_llm_models_single_default",
            "is_default",
            unique=True,
            postgresql_where=text("is_default"),
        ),
    )

    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("llm_providers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    internal_id: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_model_id: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    max_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    config_version: Mapped[str] = mapped_column(
        String(16), nullable=False, default="1", server_default="1"
    )
    capabilities: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LLMModelPrice(UUIDPrimaryKeyMixin, Base):
    """Versioned price per million tokens. Unknown price is NULL, never 0 (D-39)."""

    __tablename__ = "llm_model_prices"
    __table_args__ = (
        UniqueConstraint("model_id", "pricing_version", name="uq_llm_model_prices_version"),
        CheckConstraint(
            "(input_price_per_1m IS NULL OR input_price_per_1m >= 0) AND "
            "(output_price_per_1m IS NULL OR output_price_per_1m >= 0)",
            name="ck_llm_model_prices_non_negative",
        ),
    )

    model_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("llm_models.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    pricing_version: Mapped[str] = mapped_column(String(64), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    input_price_per_1m: Mapped[Decimal | None] = mapped_column(Numeric(14, 6), nullable=True)
    output_price_per_1m: Mapped[Decimal | None] = mapped_column(Numeric(14, 6), nullable=True)
    source_note: Mapped[str | None] = mapped_column(String(512), nullable=True)
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
