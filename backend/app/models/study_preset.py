import uuid

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class StudyPreset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A named set of study-generation defaults (Study Studio). Same fields as
    `study_generation_preferences`; a user can keep several and mark one as the default. Values are
    only defaults: a setting chosen in the generate dialog always wins."""

    __tablename__ = "study_presets"
    __table_args__ = (
        CheckConstraint(
            "explanation_level IS NULL OR "
            "explanation_level IN ('beginner', 'intermediate', 'advanced')",
            name="ck_study_presets_level",
        ),
        CheckConstraint(
            "summary_length IS NULL OR summary_length IN ('short', 'medium', 'long')",
            name="ck_study_presets_length",
        ),
        CheckConstraint(
            "question_difficulty IS NULL OR "
            "question_difficulty IN ('easy', 'medium', 'hard', 'mixed')",
            name="ck_study_presets_difficulty",
        ),
        CheckConstraint("char_length(name) BETWEEN 1 AND 60", name="ck_study_presets_name"),
        Index("ix_study_presets_user", "user_id"),
        Index(
            "uq_study_presets_user_name",
            "user_id",
            text("lower(name)"),
            unique=True,
        ),
        # at most one default preset per user
        Index(
            "uq_study_presets_one_default",
            "user_id",
            unique=True,
            postgresql_where=text("is_default"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    description: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
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
