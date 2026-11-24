"""study presets (Study Studio)

Named sets of study-generation defaults, several per user with at most one default.

Revision ID: 0028
Revises: 0027
Create Date: 2026-11-24

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "study_presets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("description", sa.String(200), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("language", sa.String(32), nullable=True),
        sa.Column("explanation_level", sa.String(16), nullable=True),
        sa.Column("summary_length", sa.String(16), nullable=True),
        sa.Column("question_difficulty", sa.String(16), nullable=True),
        sa.Column("include_examples", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "include_definitions", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "include_source_references",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "explanation_level IS NULL OR "
            "explanation_level IN ('beginner', 'intermediate', 'advanced')",
            name="ck_study_presets_level",
        ),
        sa.CheckConstraint(
            "summary_length IS NULL OR summary_length IN ('short', 'medium', 'long')",
            name="ck_study_presets_length",
        ),
        sa.CheckConstraint(
            "question_difficulty IS NULL OR "
            "question_difficulty IN ('easy', 'medium', 'hard', 'mixed')",
            name="ck_study_presets_difficulty",
        ),
        sa.CheckConstraint("char_length(name) BETWEEN 1 AND 60", name="ck_study_presets_name"),
    )
    op.create_index("ix_study_presets_user", "study_presets", ["user_id"])
    op.create_index(
        "uq_study_presets_user_name",
        "study_presets",
        ["user_id", sa.text("lower(name)")],
        unique=True,
    )
    op.create_index(
        "uq_study_presets_one_default",
        "study_presets",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )


def downgrade() -> None:
    op.drop_index("uq_study_presets_one_default", table_name="study_presets")
    op.drop_index("uq_study_presets_user_name", table_name="study_presets")
    op.drop_index("ix_study_presets_user", table_name="study_presets")
    op.drop_table("study_presets")
