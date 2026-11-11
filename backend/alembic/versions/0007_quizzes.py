"""quizzes, questions, attempts and attempt answers (Phase 4 M3)

Spec 18.6 to 18.9. `study_materials.resource_type` already allows 'quiz' since 0004. The answer
key lives only in `quiz_questions`. Grants for the restricted application role are explicit.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-11

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_TABLES = ("quizzes", "quiz_questions", "quiz_attempts", "quiz_attempt_answers")
TYPES = (
    "'multiple_choice', 'multiple_select', 'true_false', 'fill_in_the_blank', "
    "'short_answer', 'descriptive'"
)


def _ts(name: str) -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def _jsonb(name: str, default: str | None = None, nullable: bool = False) -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(
        name,
        postgresql.JSONB(astext_type=sa.Text()),
        server_default=sa.text(default) if default else None,
        nullable=nullable,
    )


def upgrade() -> None:
    op.create_table(
        "quizzes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("study_material_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("time_limit", sa.Integer(), nullable=True),
        _jsonb("settings", "'{}'::jsonb"),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["study_material_id", "user_id"],
            ["study_materials.id", "study_materials.user_id"],
            ondelete="CASCADE",
            name="fk_quizzes_material_owner",
        ),
        sa.UniqueConstraint("study_material_id", name="uq_quizzes_material"),
        sa.UniqueConstraint("id", "user_id", name="uq_quizzes_id_user"),
        sa.CheckConstraint("time_limit IS NULL OR time_limit > 0", name="ck_quizzes_time_limit"),
    )
    op.create_index(op.f("ix_quizzes_id"), "quizzes", ["id"])
    op.create_index("ix_quizzes_user", "quizzes", ["user_id"])

    op.create_table(
        "quiz_questions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("quiz_id", sa.UUID(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("question_type", sa.String(length=24), nullable=False),
        sa.Column("difficulty", sa.String(length=8), nullable=False),
        _jsonb("options", "'[]'::jsonb"),
        _jsonb("correct_answers"),
        _jsonb("rubric", "'[]'::jsonb"),
        sa.Column("explanation", sa.Text(), nullable=True),
        _jsonb("source_references", "'[]'::jsonb"),
        sa.Column("display_order", sa.Integer(), nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["quiz_id", "user_id"],
            ["quizzes.id", "quizzes.user_id"],
            ondelete="CASCADE",
            name="fk_quiz_questions_quiz_owner",
        ),
        sa.UniqueConstraint("id", "user_id", name="uq_quiz_questions_id_user"),
        sa.CheckConstraint(f"question_type IN ({TYPES})", name="ck_quiz_questions_type"),
        sa.CheckConstraint(
            "difficulty IN ('easy', 'medium', 'hard')", name="ck_quiz_questions_difficulty"
        ),
        sa.CheckConstraint("display_order >= 0", name="ck_quiz_questions_order"),
    )
    op.create_index(op.f("ix_quiz_questions_id"), "quiz_questions", ["id"])
    op.create_index("ix_quiz_questions_quiz_order", "quiz_questions", ["quiz_id", "display_order"])
    op.create_index("ix_quiz_questions_user", "quiz_questions", ["user_id"])

    op.create_table(
        "quiz_attempts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("quiz_id", sa.UUID(), nullable=False),
        sa.Column(
            "status", sa.String(length=12), server_default=sa.text("'in_progress'"), nullable=False
        ),
        _jsonb("question_order"),
        _jsonb("answers", "'{}'::jsonb"),
        _jsonb("flagged", "'[]'::jsonb"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("auto_submitted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("score", sa.Numeric(7, 2), nullable=True),
        sa.Column("total_questions", sa.Integer(), nullable=True),
        sa.Column("graded_questions", sa.Integer(), nullable=True),
        sa.Column("percentage", sa.Numeric(5, 2), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["quiz_id", "user_id"],
            ["quizzes.id", "quizzes.user_id"],
            ondelete="CASCADE",
            name="fk_quiz_attempts_quiz_owner",
        ),
        sa.UniqueConstraint("id", "user_id", name="uq_quiz_attempts_id_user"),
        sa.CheckConstraint(
            "status IN ('in_progress', 'submitted')", name="ck_quiz_attempts_status"
        ),
    )
    op.create_index(op.f("ix_quiz_attempts_id"), "quiz_attempts", ["id"])
    op.create_index(
        "ix_quiz_attempts_quiz_user", "quiz_attempts", ["quiz_id", "user_id", "started_at"]
    )
    op.create_index(
        "uq_quiz_attempts_open",
        "quiz_attempts",
        ["quiz_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'in_progress'"),
    )

    op.create_table(
        "quiz_attempt_answers",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("attempt_id", sa.UUID(), nullable=False),
        sa.Column("question_id", sa.UUID(), nullable=False),
        _jsonb("submitted_answer", nullable=True),
        sa.Column("is_correct", sa.Boolean(), nullable=True),
        sa.Column("awarded_score", sa.Numeric(5, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["attempt_id", "user_id"],
            ["quiz_attempts.id", "quiz_attempts.user_id"],
            ondelete="CASCADE",
            name="fk_quiz_attempt_answers_attempt_owner",
        ),
        sa.ForeignKeyConstraint(
            ["question_id", "user_id"],
            ["quiz_questions.id", "quiz_questions.user_id"],
            ondelete="CASCADE",
            name="fk_quiz_attempt_answers_question_owner",
        ),
        sa.UniqueConstraint("attempt_id", "question_id", name="uq_quiz_attempt_answers_pair"),
    )
    op.create_index(op.f("ix_quiz_attempt_answers_id"), "quiz_attempt_answers", ["id"])
    op.create_index("ix_quiz_attempt_answers_attempt", "quiz_attempt_answers", ["attempt_id"])

    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'axonweave_app') THEN "  # noqa: S608
        + " ".join(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON {t} TO axonweave_app;" for t in NEW_TABLES
        )
        + " END IF; END $$"
    )


def downgrade() -> None:
    op.drop_table("quiz_attempt_answers")
    op.drop_table("quiz_attempts")
    op.drop_table("quiz_questions")
    op.drop_table("quizzes")
