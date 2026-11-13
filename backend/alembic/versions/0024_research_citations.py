"""research citations (Phase 7 M7.8)

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STYLES = "'apa', 'ieee', 'mla', 'chicago', 'harvard'"


def upgrade() -> None:
    op.create_table(
        "research_citations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("research_project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("research_paper_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("citation_style", sa.String(12), nullable=False),
        sa.Column("formatted_citation", sa.Text(), nullable=False),
        sa.Column("in_text_citation", sa.String(400), nullable=False),
        sa.Column("metadata_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["research_project_id", "user_id"],
            ["research_projects.id", "research_projects.user_id"],
            name="fk_research_citations_project_owner",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["research_paper_id", "user_id"],
            ["research_papers.id", "research_papers.user_id"],
            name="fk_research_citations_paper_owner",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("id", "user_id", name="uq_research_citations_id_user"),
        sa.UniqueConstraint(
            "user_id",
            "research_project_id",
            "research_paper_id",
            "citation_style",
            name="uq_research_citations_paper_style",
        ),
        sa.CheckConstraint(f"citation_style IN ({STYLES})", name="ck_research_citations_style"),
    )
    op.create_index(
        "ix_research_citations_project", "research_citations", ["user_id", "research_project_id"]
    )


def downgrade() -> None:
    op.drop_table("research_citations")
