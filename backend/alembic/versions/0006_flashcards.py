"""flashcard sets and flashcards (Phase 4 M2)

Creates `flashcard_sets` and `flashcards` (spec 18.4, 18.5). `study_materials.resource_type`
already allows 'flashcards' since 0004. Grants for the restricted application role are explicit.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-11

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_TABLES = ("flashcard_sets", "flashcards")
CARD_TYPES = "'basic', 'definition', 'concept', 'comparison', 'fill_in_the_blank', 'application'"


def _ts(name: str) -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "flashcard_sets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("study_material_id", sa.UUID(), nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["study_material_id", "user_id"],
            ["study_materials.id", "study_materials.user_id"],
            ondelete="CASCADE",
            name="fk_flashcard_sets_material_owner",
        ),
        sa.UniqueConstraint("study_material_id", name="uq_flashcard_sets_material"),
        sa.UniqueConstraint("id", "user_id", name="uq_flashcard_sets_id_user"),
    )
    op.create_index(op.f("ix_flashcard_sets_id"), "flashcard_sets", ["id"])
    op.create_index("ix_flashcard_sets_user", "flashcard_sets", ["user_id"])
    op.create_table(
        "flashcards",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("flashcard_set_id", sa.UUID(), nullable=False),
        sa.Column("front", sa.Text(), nullable=False),
        sa.Column("back", sa.Text(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("card_type", sa.String(length=24), nullable=False),
        sa.Column("difficulty", sa.String(length=8), nullable=False),
        sa.Column(
            "source_references",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("is_favourite", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "origin", sa.String(length=10), server_default=sa.text("'generated'"), nullable=False
        ),
        sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["flashcard_set_id", "user_id"],
            ["flashcard_sets.id", "flashcard_sets.user_id"],
            ondelete="CASCADE",
            name="fk_flashcards_set_owner",
        ),
        sa.CheckConstraint(f"card_type IN ({CARD_TYPES})", name="ck_flashcards_type"),
        sa.CheckConstraint(
            "difficulty IN ('easy', 'medium', 'hard')", name="ck_flashcards_difficulty"
        ),
        sa.CheckConstraint("origin IN ('generated', 'manual')", name="ck_flashcards_origin"),
        sa.CheckConstraint("display_order >= 0", name="ck_flashcards_order"),
    )
    op.create_index(op.f("ix_flashcards_id"), "flashcards", ["id"])
    op.create_index("ix_flashcards_set_order", "flashcards", ["flashcard_set_id", "display_order"])
    op.create_index("ix_flashcards_user", "flashcards", ["user_id"])

    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'axonweave_app') THEN "  # noqa: S608
        + " ".join(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON {t} TO axonweave_app;" for t in NEW_TABLES
        )
        + " END IF; END $$"
    )


def downgrade() -> None:
    op.drop_table("flashcards")
    op.drop_table("flashcard_sets")
