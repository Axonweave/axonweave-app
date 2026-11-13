"""research contradictions (Phase 7 M7.7)

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CATEGORIES = "'genuine', 'context_dependent', 'metric_incompatible', 'insufficient_evidence'"
CONFIDENCE = "'moderate', 'low'"
REVIEW = "'unreviewed', 'genuine', 'context_dependent', 'dismissed'"


def _uuid(name: str, nullable: bool = False) -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=nullable)


def _ts(name: str) -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "research_contradictions",
        _uuid("id"),
        _uuid("user_id"),
        _uuid("research_project_id"),
        _uuid("paper_a_id"),
        _uuid("paper_b_id"),
        sa.Column("claim_a_text", sa.Text(), nullable=False),
        sa.Column("claim_b_text", sa.Text(), nullable=False),
        sa.Column("claim_a_type", sa.String(24), nullable=False),
        sa.Column("claim_b_type", sa.String(24), nullable=False),
        _uuid("evidence_a_id", nullable=True),
        _uuid("evidence_b_id", nullable=True),
        sa.Column("quote_a", sa.Text(), nullable=True),
        sa.Column("quote_b", sa.Text(), nullable=True),
        sa.Column("page_a", sa.Integer(), nullable=True),
        sa.Column("page_b", sa.Integer(), nullable=True),
        sa.Column(
            "conditions",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("category", sa.String(24), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("confidence_label", sa.String(10), nullable=False),
        sa.Column("review_status", sa.String(24), nullable=False),
        sa.Column("researcher_explanation", sa.Text(), nullable=True),
        sa.Column("analysis_version", sa.String(16), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["research_project_id", "user_id"],
            ["research_projects.id", "research_projects.user_id"],
            name="fk_research_contradictions_project_owner",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["paper_a_id", "user_id"],
            ["research_papers.id", "research_papers.user_id"],
            name="fk_research_contradictions_paper_a_owner",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["paper_b_id", "user_id"],
            ["research_papers.id", "research_papers.user_id"],
            name="fk_research_contradictions_paper_b_owner",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["evidence_a_id"], ["research_evidence.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["evidence_b_id"], ["research_evidence.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("id", "user_id", name="uq_research_contradictions_id_user"),
        sa.CheckConstraint(f"category IN ({CATEGORIES})", name="ck_research_contradictions_cat"),
        sa.CheckConstraint(
            f"confidence_label IN ({CONFIDENCE})", name="ck_research_contradictions_conf"
        ),
        sa.CheckConstraint(
            f"review_status IN ({REVIEW})", name="ck_research_contradictions_review"
        ),
    )
    op.create_index(
        "ix_research_contradictions_project",
        "research_contradictions",
        ["user_id", "research_project_id", "review_status"],
    )


def downgrade() -> None:
    op.drop_table("research_contradictions")
