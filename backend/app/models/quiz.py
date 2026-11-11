import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

QUESTION_TYPES = (
    "multiple_choice",
    "multiple_select",
    "true_false",
    "fill_in_the_blank",
    "short_answer",
    "descriptive",
)
_TYPE_SQL = ", ".join(f"'{t}'" for t in QUESTION_TYPES)


class Quiz(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One generated quiz (spec 18.6); the questions and their answer keys are in `quiz_questions`.
    `time_limit` is in seconds (NULL = untimed)."""

    __tablename__ = "quizzes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["study_material_id", "user_id"],
            ["study_materials.id", "study_materials.user_id"],
            ondelete="CASCADE",
            name="fk_quizzes_material_owner",
        ),
        UniqueConstraint("study_material_id", name="uq_quizzes_material"),
        UniqueConstraint("id", "user_id", name="uq_quizzes_id_user"),
        CheckConstraint("time_limit IS NULL OR time_limit > 0", name="ck_quizzes_time_limit"),
        Index("ix_quizzes_user", "user_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    study_material_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    time_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    settings: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )


class QuizQuestion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One question (spec 18.7). `correct_answers`, `explanation` and `rubric` are the answer key:
    they are read only by grading and by the results of a SUBMITTED attempt (D-82, D-94)."""

    __tablename__ = "quiz_questions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["quiz_id", "user_id"],
            ["quizzes.id", "quizzes.user_id"],
            ondelete="CASCADE",
            name="fk_quiz_questions_quiz_owner",
        ),
        UniqueConstraint("id", "user_id", name="uq_quiz_questions_id_user"),
        CheckConstraint(f"question_type IN ({_TYPE_SQL})", name="ck_quiz_questions_type"),
        CheckConstraint(
            "difficulty IN ('easy', 'medium', 'hard')", name="ck_quiz_questions_difficulty"
        ),
        CheckConstraint("display_order >= 0", name="ck_quiz_questions_order"),
        Index("ix_quiz_questions_quiz_order", "quiz_id", "display_order"),
        Index("ix_quiz_questions_user", "user_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    quiz_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    question_type: Mapped[str] = mapped_column(String(24), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(8), nullable=False)
    options: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    correct_answers: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    rubric: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_references: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)


class QuizAttempt(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One attempt (spec 18.8). While in progress `answers` holds the saved answers; submitting
    freezes it. `expires_at` is the server-side deadline (NULL = untimed)."""

    __tablename__ = "quiz_attempts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["quiz_id", "user_id"],
            ["quizzes.id", "quizzes.user_id"],
            ondelete="CASCADE",
            name="fk_quiz_attempts_quiz_owner",
        ),
        UniqueConstraint("id", "user_id", name="uq_quiz_attempts_id_user"),
        CheckConstraint("status IN ('in_progress', 'submitted')", name="ck_quiz_attempts_status"),
        Index("ix_quiz_attempts_quiz_user", "quiz_id", "user_id", "started_at"),
        # at most one open attempt per quiz and user (resume instead of a second one)
        Index(
            "uq_quiz_attempts_open",
            "quiz_id",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'in_progress'"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    quiz_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, default="in_progress", server_default=text("'in_progress'")
    )
    question_order: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    answers: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    flagged: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    auto_submitted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    score: Mapped[Decimal | None] = mapped_column(Numeric(7, 2), nullable=True)
    total_questions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    graded_questions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    percentage: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)


class QuizAttemptAnswer(UUIDPrimaryKeyMixin, Base):
    """Per-question result of a submitted attempt (spec 18.9). `is_correct` is NULL for questions
    that are not auto-graded (short answer, descriptive)."""

    __tablename__ = "quiz_attempt_answers"
    __table_args__ = (
        ForeignKeyConstraint(
            ["attempt_id", "user_id"],
            ["quiz_attempts.id", "quiz_attempts.user_id"],
            ondelete="CASCADE",
            name="fk_quiz_attempt_answers_attempt_owner",
        ),
        ForeignKeyConstraint(
            ["question_id", "user_id"],
            ["quiz_questions.id", "quiz_questions.user_id"],
            ondelete="CASCADE",
            name="fk_quiz_attempt_answers_question_owner",
        ),
        UniqueConstraint("attempt_id", "question_id", name="uq_quiz_attempt_answers_pair"),
        Index("ix_quiz_attempt_answers_attempt", "attempt_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    attempt_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    question_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    submitted_answer: Mapped[Any] = mapped_column(JSONB, nullable=True)
    is_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    awarded_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal(0), server_default=text("0")
    )
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
