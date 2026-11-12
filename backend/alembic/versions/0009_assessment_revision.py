"""assessment and revision foundation (Phase 5 M0)

Extends `quiz_attempts`, `quiz_attempt_answers`, `quiz_questions` and `flashcards` (topic labels,
counts, evaluation status, idempotency key) and adds `flashcard_scheduling`, `flashcard_reviews`,
`revision_sessions` and `revision_recommendations` (D-102 to D-110). Existing rows are kept: new
columns are nullable or have defaults, and simple counts are backfilled from stored answers.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-12

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_TABLES = (
    "revision_sessions",
    "flashcard_scheduling",
    "flashcard_reviews",
    "revision_recommendations",
)
STATES = "'new', 'learning', 'review', 'relearning'"
RATINGS = "'again', 'hard', 'good', 'easy'"


def _ts(name: str) -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def _tstz(name: str, nullable: bool = True) -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def _int0(name: str) -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(name, sa.Integer(), server_default=sa.text("0"), nullable=False)


def upgrade() -> None:
    # ── topic labels (D-102) ──────────────────────────────────────────────────────────────
    op.add_column("quiz_questions", sa.Column("topic", sa.String(length=120), nullable=True))
    op.create_index("ix_quiz_questions_user_topic", "quiz_questions", ["user_id", "topic"])
    op.add_column("flashcards", sa.Column("topic", sa.String(length=120), nullable=True))
    op.create_unique_constraint("uq_flashcards_id_user", "flashcards", ["id", "user_id"])

    # ── quiz_attempts (D-103) ─────────────────────────────────────────────────────────────
    op.drop_constraint("ck_quiz_attempts_status", "quiz_attempts", type_="check")
    op.create_check_constraint(
        "ck_quiz_attempts_status",
        "quiz_attempts",
        "status IN ('in_progress', 'submitted', 'abandoned')",
    )
    op.add_column("quiz_attempts", sa.Column("correct_answers", sa.Integer(), nullable=True))
    op.add_column("quiz_attempts", sa.Column("incorrect_answers", sa.Integer(), nullable=True))
    op.add_column("quiz_attempts", sa.Column("unanswered", sa.Integer(), nullable=True))
    op.add_column("quiz_attempts", sa.Column("max_score", sa.Numeric(7, 2), nullable=True))
    op.add_column("quiz_attempts", sa.Column("time_taken_seconds", sa.Integer(), nullable=True))
    op.add_column("quiz_attempts", _tstz("abandoned_at"))
    op.add_column(
        "quiz_attempts",
        sa.Column(
            "evaluation_status",
            sa.String(length=12),
            server_default=sa.text("'not_required'"),
            nullable=False,
        ),
    )
    op.add_column(
        "quiz_attempts", sa.Column("submit_idempotency_key", sa.String(length=64), nullable=True)
    )
    op.create_check_constraint(
        "ck_quiz_attempts_evaluation_status",
        "quiz_attempts",
        "evaluation_status IN ('not_required', 'pending', 'completed', 'failed')",
    )
    op.create_check_constraint(
        "ck_quiz_attempts_time_taken",
        "quiz_attempts",
        "time_taken_seconds IS NULL OR time_taken_seconds >= 0",
    )
    op.create_index(
        "uq_quiz_attempts_submit_key",
        "quiz_attempts",
        ["user_id", "submit_idempotency_key"],
        unique=True,
        postgresql_where=sa.text("submit_idempotency_key IS NOT NULL"),
    )
    op.create_index("ix_quiz_attempts_user_submitted", "quiz_attempts", ["user_id", "submitted_at"])
    # Backfill what the stored answers prove (objective questions are 1 point each, D-96).
    op.execute(
        "UPDATE quiz_attempts a SET "  # noqa: S608
        "correct_answers = s.c, incorrect_answers = s.i, max_score = a.graded_questions "
        "FROM (SELECT attempt_id, "
        "count(*) FILTER (WHERE is_correct IS TRUE) AS c, "
        "count(*) FILTER (WHERE is_correct IS FALSE) AS i "
        "FROM quiz_attempt_answers GROUP BY attempt_id) s "
        "WHERE s.attempt_id = a.id AND a.status = 'submitted'"
    )
    op.execute(
        "UPDATE quiz_attempts SET time_taken_seconds = GREATEST(0, LEAST("
        "extract(epoch FROM (submitted_at - started_at))::int, "
        "COALESCE(extract(epoch FROM (expires_at - started_at))::int, 2147483647))) "
        "WHERE status = 'submitted' AND submitted_at IS NOT NULL"
    )

    # ── quiz_attempt_answers (D-104) ──────────────────────────────────────────────────────
    op.add_column(
        "quiz_attempt_answers",
        sa.Column("max_score", sa.Numeric(5, 2), server_default=sa.text("1"), nullable=False),
    )
    op.add_column(
        "quiz_attempt_answers",
        sa.Column(
            "grading_method", sa.String(length=16), server_default=sa.text("'auto'"), nullable=False
        ),
    )
    op.add_column(
        "quiz_attempt_answers",
        sa.Column(
            "evaluation_status",
            sa.String(length=12),
            server_default=sa.text("'graded'"),
            nullable=False,
        ),
    )
    op.add_column(
        "quiz_attempt_answers",
        sa.Column("ai_assisted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "quiz_attempt_answers",
        sa.Column("evaluation_detail", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "quiz_attempt_answers",
        sa.Column("evaluation_error_code", sa.String(length=48), nullable=True),
    )
    op.add_column("quiz_attempt_answers", _tstz("evaluated_at"))
    # Phase 4 stored short-answer and descriptive rows with is_correct NULL: mark them honestly.
    op.execute(
        "UPDATE quiz_attempt_answers SET grading_method = 'self_assessment', "
        "evaluation_status = 'not_graded', max_score = 0 WHERE is_correct IS NULL"
    )
    op.execute("UPDATE quiz_attempt_answers SET evaluated_at = submitted_at")
    op.create_check_constraint(
        "ck_quiz_attempt_answers_grading_method",
        "quiz_attempt_answers",
        "grading_method IN ('auto', 'ai', 'self_assessment')",
    )
    op.create_check_constraint(
        "ck_quiz_attempt_answers_evaluation_status",
        "quiz_attempt_answers",
        "evaluation_status IN ('graded', 'not_graded', 'pending', 'failed')",
    )
    op.create_index(
        "ix_quiz_attempt_answers_user_question", "quiz_attempt_answers", ["user_id", "question_id"]
    )

    # ── revision_sessions (spec 4.5) ──────────────────────────────────────────────────────
    op.create_table(
        "revision_sessions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("subject_id", sa.UUID(), nullable=True),
        sa.Column("chapter_id", sa.UUID(), nullable=True),
        sa.Column(
            "status", sa.String(length=12), server_default=sa.text("'active'"), nullable=False
        ),
        _tstz("started_at", nullable=False),
        _tstz("completed_at"),
        _tstz("last_activity_at", nullable=False),
        _int0("total_cards"),
        _int0("reviewed_cards"),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column(
            "card_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        _ts("created_at"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("id", "user_id", name="uq_revision_sessions_id_user"),
        sa.CheckConstraint(
            "status IN ('active', 'completed', 'abandoned')", name="ck_revision_sessions_status"
        ),
        sa.CheckConstraint(
            "total_cards >= 0 AND reviewed_cards >= 0 AND reviewed_cards <= total_cards",
            name="ck_revision_sessions_counts",
        ),
        sa.CheckConstraint(
            "duration_seconds IS NULL OR duration_seconds >= 0",
            name="ck_revision_sessions_duration",
        ),
    )
    op.execute(
        "ALTER TABLE revision_sessions ADD CONSTRAINT fk_revision_sessions_chapter_subject "
        "FOREIGN KEY (chapter_id, subject_id) REFERENCES chapters (id, subject_id) "
        "ON DELETE SET NULL (chapter_id)"
    )
    op.create_index("ix_revision_sessions_id", "revision_sessions", ["id"])
    op.create_index(
        "ix_revision_sessions_user_started", "revision_sessions", ["user_id", "started_at"]
    )
    op.create_index(
        "uq_revision_sessions_active",
        "revision_sessions",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    # ── flashcard_scheduling (spec 4.3) ───────────────────────────────────────────────────
    op.create_table(
        "flashcard_scheduling",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("flashcard_id", sa.UUID(), nullable=False),
        sa.Column("state", sa.String(length=12), server_default=sa.text("'new'"), nullable=False),
        sa.Column("step", sa.Integer(), nullable=True),
        _tstz("due_at", nullable=False),
        sa.Column("stability", sa.Float(), nullable=True),
        sa.Column("difficulty", sa.Float(), nullable=True),
        _int0("elapsed_days"),
        _int0("scheduled_days"),
        _int0("repetitions"),
        _int0("lapses"),
        sa.Column("suspended", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        _tstz("last_review_at"),
        sa.Column("scheduler_version", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["flashcard_id", "user_id"],
            ["flashcards.id", "flashcards.user_id"],
            ondelete="CASCADE",
            name="fk_flashcard_scheduling_card_owner",
        ),
        sa.UniqueConstraint("user_id", "flashcard_id", name="uq_flashcard_scheduling_user_card"),
        sa.CheckConstraint(f"state IN ({STATES})", name="ck_flashcard_scheduling_state"),
        sa.CheckConstraint(
            "repetitions >= 0 AND lapses >= 0 AND elapsed_days >= 0 AND scheduled_days >= 0",
            name="ck_flashcard_scheduling_counts",
        ),
        sa.CheckConstraint("step IS NULL OR step >= 0", name="ck_flashcard_scheduling_step"),
    )
    op.create_index("ix_flashcard_scheduling_id", "flashcard_scheduling", ["id"])
    op.create_index(
        "ix_flashcard_scheduling_user_due", "flashcard_scheduling", ["user_id", "due_at"]
    )
    op.create_index(
        "ix_flashcard_scheduling_user_state", "flashcard_scheduling", ["user_id", "state"]
    )
    op.create_index("ix_flashcard_scheduling_card", "flashcard_scheduling", ["flashcard_id"])

    # ── flashcard_reviews (spec 4.4) ──────────────────────────────────────────────────────
    op.create_table(
        "flashcard_reviews",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("flashcard_id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("rating", sa.String(length=8), nullable=False),
        _tstz("reviewed_at", nullable=False),
        sa.Column("elapsed_days", sa.Integer(), nullable=False),
        sa.Column("scheduled_days", sa.Integer(), nullable=False),
        sa.Column("response_time_ms", sa.Integer(), nullable=True),
        sa.Column("previous_state", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("resulting_state", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("scheduler_version", sa.String(length=32), nullable=False),
        _ts("created_at"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["flashcard_id", "user_id"],
            ["flashcards.id", "flashcards.user_id"],
            ondelete="CASCADE",
            name="fk_flashcard_reviews_card_owner",
        ),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_flashcard_reviews_user_key"),
        sa.CheckConstraint(f"rating IN ({RATINGS})", name="ck_flashcard_reviews_rating"),
        sa.CheckConstraint(
            "response_time_ms IS NULL OR response_time_ms >= 0",
            name="ck_flashcard_reviews_response_time",
        ),
    )
    op.execute(
        "ALTER TABLE flashcard_reviews ADD CONSTRAINT fk_flashcard_reviews_session_owner "
        "FOREIGN KEY (session_id, user_id) REFERENCES revision_sessions (id, user_id) "
        "ON DELETE SET NULL (session_id)"
    )
    op.create_index("ix_flashcard_reviews_id", "flashcard_reviews", ["id"])
    op.create_index(
        "ix_flashcard_reviews_user_reviewed", "flashcard_reviews", ["user_id", "reviewed_at"]
    )
    op.create_index(
        "ix_flashcard_reviews_card_reviewed", "flashcard_reviews", ["flashcard_id", "reviewed_at"]
    )
    op.create_index("ix_flashcard_reviews_session", "flashcard_reviews", ["session_id"])

    # ── revision_recommendations (spec 4.7) ───────────────────────────────────────────────
    op.create_table(
        "revision_recommendations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("recommendation_type", sa.String(length=12), nullable=False),
        sa.Column("target_id", sa.UUID(), nullable=True),
        sa.Column("topic_name", sa.String(length=120), nullable=True),
        sa.Column("dedupe_key", sa.String(length=160), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(length=8), nullable=False),
        sa.Column(
            "status", sa.String(length=10), server_default=sa.text("'pending'"), nullable=False
        ),
        _ts("created_at"),
        _tstz("completed_at"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "recommendation_type IN ('quiz', 'flashcard', 'topic', 'chapter')",
            name="ck_revision_recommendations_type",
        ),
        sa.CheckConstraint(
            "priority IN ('low', 'medium', 'high')", name="ck_revision_recommendations_priority"
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'completed', 'dismissed')",
            name="ck_revision_recommendations_status",
        ),
    )
    op.create_index("ix_revision_recommendations_id", "revision_recommendations", ["id"])
    op.create_index(
        "ix_revision_recommendations_user_status",
        "revision_recommendations",
        ["user_id", "status", "created_at"],
    )
    op.create_index(
        "uq_revision_recommendations_pending",
        "revision_recommendations",
        ["user_id", "dedupe_key"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )

    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'axonweave_app') THEN "  # noqa: S608
        + " ".join(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON {t} TO axonweave_app;" for t in NEW_TABLES
        )
        + " END IF; END $$"
    )


def downgrade() -> None:
    # Dropping the new tables discards review history by design; the Phase 4 data stays.
    op.drop_table("revision_recommendations")
    op.drop_table("flashcard_reviews")
    op.drop_table("flashcard_scheduling")
    op.drop_table("revision_sessions")

    op.drop_index("ix_quiz_attempt_answers_user_question", table_name="quiz_attempt_answers")
    op.drop_constraint(
        "ck_quiz_attempt_answers_evaluation_status", "quiz_attempt_answers", type_="check"
    )
    op.drop_constraint(
        "ck_quiz_attempt_answers_grading_method", "quiz_attempt_answers", type_="check"
    )
    for col in (
        "evaluated_at",
        "evaluation_error_code",
        "evaluation_detail",
        "ai_assisted",
        "evaluation_status",
        "grading_method",
        "max_score",
    ):
        op.drop_column("quiz_attempt_answers", col)

    op.drop_index("ix_quiz_attempts_user_submitted", table_name="quiz_attempts")
    op.drop_index("uq_quiz_attempts_submit_key", table_name="quiz_attempts")
    op.drop_constraint("ck_quiz_attempts_time_taken", "quiz_attempts", type_="check")
    op.drop_constraint("ck_quiz_attempts_evaluation_status", "quiz_attempts", type_="check")
    # abandoned attempts cannot exist in the old status set: they become submitted-less, so remove
    # them (they hold no result) before restoring the narrower constraint.
    op.execute("DELETE FROM quiz_attempts WHERE status = 'abandoned'")
    op.drop_constraint("ck_quiz_attempts_status", "quiz_attempts", type_="check")
    op.create_check_constraint(
        "ck_quiz_attempts_status", "quiz_attempts", "status IN ('in_progress', 'submitted')"
    )
    for col in (
        "submit_idempotency_key",
        "evaluation_status",
        "abandoned_at",
        "time_taken_seconds",
        "max_score",
        "unanswered",
        "incorrect_answers",
        "correct_answers",
    ):
        op.drop_column("quiz_attempts", col)

    op.drop_constraint("uq_flashcards_id_user", "flashcards", type_="unique")
    op.drop_column("flashcards", "topic")
    op.drop_index("ix_quiz_questions_user_topic", table_name="quiz_questions")
    op.drop_column("quiz_questions", "topic")
