import uuid

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class StudyGenerationPreferences(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """User-chosen generation defaults (spec 16). Only what the user sets; nothing is inferred.
    Kept apart from `user_preferences` (Phase 1 reserved fields). Endpoints arrive in M5."""

    __tablename__ = "study_generation_preferences"
    __table_args__ = (
        CheckConstraint(
            "explanation_level IS NULL OR "
            "explanation_level IN ('beginner', 'intermediate', 'advanced')",
            name="ck_study_prefs_level",
        ),
        CheckConstraint(
            "summary_length IS NULL OR summary_length IN ('short', 'medium', 'long')",
            name="ck_study_prefs_length",
        ),
        CheckConstraint(
            "question_difficulty IS NULL OR "
            "question_difficulty IN ('easy', 'medium', 'hard', 'mixed')",
            name="ck_study_prefs_difficulty",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    language: Mapped[str | None] = mapped_column(String(32), nullable=True)
    explanation_level: Mapped[str | None] = mapped_column(String(16), nullable=True)
    summary_length: Mapped[str | None] = mapped_column(String(16), nullable=True)
    question_difficulty: Mapped[str | None] = mapped_column(String(16), nullable=True)
    include_examples: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    include_definitions: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    include_source_references: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
