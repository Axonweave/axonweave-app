import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


class UserPreferences(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """D-06: reserved fields only; no logic in Phase 1."""

    __tablename__ = "user_preferences"
    __table_args__ = (
        CheckConstraint(
            "theme IN ('light', 'dark', 'system')",
            name="ck_user_preferences_theme",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    theme: Mapped[str] = mapped_column(String(16), nullable=False, default="system")
    explanation_style: Mapped[str | None] = mapped_column(String(64), nullable=True)
    academic_level: Mapped[str | None] = mapped_column(String(64), nullable=True)
    study_preferences: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    preferred_language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    # Set when the user acknowledges the AI data-handling notice (Phase 2).
    ai_notice_acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped["User"] = relationship("User", back_populates="preferences")
