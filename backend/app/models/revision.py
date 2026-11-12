"""Phase 5 spaced-repetition and revision tables (spec 4.3 to 4.5, 4.7; D-105 to D-110).

`flashcard_scheduling` is the current FSRS state of one card for its owner; `flashcard_reviews` is
the append-only event log (the scheduling row can be rebuilt from it). Deleting a flashcard deletes
both (D-110). Ownership is enforced in the database by composite foreign keys on `(id, user_id)`.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.database.fk import SetNullColumnsFK

CARD_STATES = ("new", "learning", "review", "relearning")
RATINGS = ("again", "hard", "good", "easy")
_STATE_SQL = ", ".join(f"'{s}'" for s in CARD_STATES)
_RATING_SQL = ", ".join(f"'{r}'" for r in RATINGS)


class FlashcardScheduling(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Current scheduling state of one card (spec 4.3). Created lazily (M3). `stability` and
    `difficulty` are NULL until the first review. `version` counts writes (optimistic check)."""

    __tablename__ = "flashcard_scheduling"
    __table_args__ = (
        ForeignKeyConstraint(
            ["flashcard_id", "user_id"],
            ["flashcards.id", "flashcards.user_id"],
            ondelete="CASCADE",
            name="fk_flashcard_scheduling_card_owner",
        ),
        UniqueConstraint("user_id", "flashcard_id", name="uq_flashcard_scheduling_user_card"),
        CheckConstraint(f"state IN ({_STATE_SQL})", name="ck_flashcard_scheduling_state"),
        CheckConstraint(
            "repetitions >= 0 AND lapses >= 0 AND elapsed_days >= 0 AND scheduled_days >= 0",
            name="ck_flashcard_scheduling_counts",
        ),
        CheckConstraint("step IS NULL OR step >= 0", name="ck_flashcard_scheduling_step"),
        Index("ix_flashcard_scheduling_user_due", "user_id", "due_at"),
        Index("ix_flashcard_scheduling_user_state", "user_id", "state"),
        Index("ix_flashcard_scheduling_card", "flashcard_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    flashcard_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    state: Mapped[str] = mapped_column(
        String(12), nullable=False, default="new", server_default=text("'new'")
    )
    step: Mapped[int | None] = mapped_column(Integer, nullable=True)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    stability: Mapped[float | None] = mapped_column(Float, nullable=True)
    difficulty: Mapped[float | None] = mapped_column(Float, nullable=True)
    elapsed_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    scheduled_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    repetitions: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    lapses: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    suspended: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    last_review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Which parameter set produced this state (D-107); history is kept when parameters change.
    scheduler_version: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )


class RevisionSession(UUIDPrimaryKeyMixin, Base):
    """One flashcard revision session (spec 4.5). `subject_id`/`chapter_id` are cleared when those
    are deleted; the service validates that the subject belongs to the user before use."""

    __tablename__ = "revision_sessions"
    __table_args__ = (
        SetNullColumnsFK(
            ["chapter_id", "subject_id"],
            ["chapters.id", "chapters.subject_id"],
            set_null=["chapter_id"],
            name="fk_revision_sessions_chapter_subject",
        ),
        UniqueConstraint("id", "user_id", name="uq_revision_sessions_id_user"),
        CheckConstraint(
            "status IN ('active', 'completed', 'abandoned')", name="ck_revision_sessions_status"
        ),
        CheckConstraint(
            "total_cards >= 0 AND reviewed_cards >= 0 AND reviewed_cards <= total_cards",
            name="ck_revision_sessions_counts",
        ),
        CheckConstraint(
            "duration_seconds IS NULL OR duration_seconds >= 0",
            name="ck_revision_sessions_duration",
        ),
        Index("ix_revision_sessions_user_started", "user_id", "started_at"),
        # at most one active session per user (resume instead of a second one)
        Index(
            "uq_revision_sessions_active",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    subject_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subjects.id", ondelete="SET NULL"), nullable=True
    )
    chapter_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, default="active", server_default=text("'active'")
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    total_cards: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    reviewed_cards: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Card ids chosen at start (ids only, D-82). Cards deleted later are skipped.
    card_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class FlashcardReview(UUIDPrimaryKeyMixin, Base):
    """One review event (spec 4.4), append-only. `idempotency_key` makes a retried request return
    the stored event instead of reviewing twice (D-109)."""

    __tablename__ = "flashcard_reviews"
    __table_args__ = (
        ForeignKeyConstraint(
            ["flashcard_id", "user_id"],
            ["flashcards.id", "flashcards.user_id"],
            ondelete="CASCADE",
            name="fk_flashcard_reviews_card_owner",
        ),
        SetNullColumnsFK(
            ["session_id", "user_id"],
            ["revision_sessions.id", "revision_sessions.user_id"],
            set_null=["session_id"],
            name="fk_flashcard_reviews_session_owner",
        ),
        UniqueConstraint("user_id", "idempotency_key", name="uq_flashcard_reviews_user_key"),
        CheckConstraint(f"rating IN ({_RATING_SQL})", name="ck_flashcard_reviews_rating"),
        CheckConstraint(
            "response_time_ms IS NULL OR response_time_ms >= 0",
            name="ck_flashcard_reviews_response_time",
        ),
        Index("ix_flashcard_reviews_user_reviewed", "user_id", "reviewed_at"),
        Index("ix_flashcard_reviews_card_reviewed", "flashcard_id", "reviewed_at"),
        Index("ix_flashcard_reviews_session", "session_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    flashcard_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    rating: Mapped[str] = mapped_column(String(8), nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    elapsed_days: Mapped[int] = mapped_column(Integer, nullable=False)
    scheduled_days: Mapped[int] = mapped_column(Integer, nullable=False)
    response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    previous_state: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    resulting_state: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    scheduler_version: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class RevisionRecommendation(UUIDPrimaryKeyMixin, Base):
    """A stored recommendation (spec 4.7). `target_id` is intentionally not a foreign key because
    it can point at a quiz, flashcard, subject or chapter; the service validates ownership when
    reading and skips targets that no longer exist. `dedupe_key` is unique while pending."""

    __tablename__ = "revision_recommendations"
    __table_args__ = (
        CheckConstraint(
            "recommendation_type IN ('quiz', 'flashcard', 'topic', 'chapter')",
            name="ck_revision_recommendations_type",
        ),
        CheckConstraint(
            "priority IN ('low', 'medium', 'high')", name="ck_revision_recommendations_priority"
        ),
        CheckConstraint(
            "status IN ('pending', 'completed', 'dismissed')",
            name="ck_revision_recommendations_status",
        ),
        Index("ix_revision_recommendations_user_status", "user_id", "status", "created_at"),
        Index(
            "uq_revision_recommendations_pending",
            "user_id",
            "dedupe_key",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    recommendation_type: Mapped[str] = mapped_column(String(12), nullable=False)
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    topic_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    dedupe_key: Mapped[str] = mapped_column(String(160), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(
        String(10), nullable=False, default="pending", server_default=text("'pending'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
