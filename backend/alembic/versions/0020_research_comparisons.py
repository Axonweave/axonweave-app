"""research comparisons (Phase 7 M7.4)

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid(name: str, nullable: bool = False) -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=nullable)


def _ts(name: str) -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "research_comparisons",
        _uuid("id"),
        _uuid("user_id"),
        _uuid("research_project_id"),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("comparison_configuration", postgresql.JSONB(), nullable=False),
        sa.Column("comparison_result", postgresql.JSONB(), nullable=False),
        sa.Column("notes", postgresql.JSONB(), nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["research_project_id", "user_id"],
            ["research_projects.id", "research_projects.user_id"],
            name="fk_research_comparisons_project_owner",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("id", "user_id", name="uq_research_comparisons_id_user"),
    )
    op.create_index(
        "ix_research_comparisons_project",
        "research_comparisons",
        ["user_id", "research_project_id", "created_at"],
    )
    op.create_table(
        "research_comparison_papers",
        _uuid("id"),
        _uuid("user_id"),
        _uuid("comparison_id"),
        _uuid("research_paper_id"),
        _uuid("extraction_id", nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["comparison_id", "user_id"],
            ["research_comparisons.id", "research_comparisons.user_id"],
            name="fk_research_comparison_papers_cmp_owner",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["research_paper_id", "user_id"],
            ["research_papers.id", "research_papers.user_id"],
            name="fk_research_comparison_papers_paper_owner",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("comparison_id", "research_paper_id", name="uq_research_cmp_paper"),
    )


def downgrade() -> None:
    op.drop_table("research_comparison_papers")
    op.drop_table("research_comparisons")
