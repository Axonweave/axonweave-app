"""research gaps (Phase 7 M7.6)

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CATEGORIES = (
    "'methodological', 'dataset', 'population', 'evaluation', 'domain', 'application', "
    "'generalisation', 'reproducibility', 'contradictory_findings'"
)
CONFIDENCE = (
    "'strong_candidate', 'moderate_candidate', 'preliminary_candidate', 'insufficient_evidence'"
)
STATUSES = "'suggested', 'accepted', 'rejected', 'investigating'"
ROLES = "'supporting', 'counter_evidence', 'contextual'"


def _uuid(name: str, nullable: bool = False) -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=nullable)


def _ts(name: str) -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "research_gaps",
        _uuid("id"),
        _uuid("user_id"),
        _uuid("research_project_id"),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("confidence_label", sa.String(24), nullable=False),
        sa.Column("limitations", sa.Text(), nullable=False),
        sa.Column("suggested_direction", sa.Text(), nullable=False),
        sa.Column("validation_status", sa.String(14), nullable=False),
        sa.Column("analysis_version", sa.String(16), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("edited_by_user", sa.Boolean(), nullable=False),
        sa.Column("researcher_notes", sa.Text(), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["research_project_id", "user_id"],
            ["research_projects.id", "research_projects.user_id"],
            name="fk_research_gaps_project_owner",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("id", "user_id", name="uq_research_gaps_id_user"),
        sa.CheckConstraint(f"category IN ({CATEGORIES})", name="ck_research_gaps_category"),
        sa.CheckConstraint(
            f"confidence_label IN ({CONFIDENCE})", name="ck_research_gaps_confidence"
        ),
        sa.CheckConstraint(f"validation_status IN ({STATUSES})", name="ck_research_gaps_status"),
    )
    op.create_index(
        "ix_research_gaps_project",
        "research_gaps",
        ["user_id", "research_project_id", "validation_status"],
    )
    op.create_table(
        "research_gap_evidence",
        _uuid("id"),
        _uuid("user_id"),
        _uuid("gap_id"),
        _uuid("research_paper_id"),
        _uuid("research_evidence_id", nullable=True),
        sa.Column("evidence_role", sa.String(16), nullable=False),
        sa.Column("claim_type", sa.String(24), nullable=False),
        sa.Column("claim_text", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["gap_id", "user_id"],
            ["research_gaps.id", "research_gaps.user_id"],
            name="fk_research_gap_evidence_gap_owner",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["research_paper_id", "user_id"],
            ["research_papers.id", "research_papers.user_id"],
            name="fk_research_gap_evidence_paper_owner",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["research_evidence_id"], ["research_evidence.id"], ondelete="SET NULL"
        ),
        sa.CheckConstraint(f"evidence_role IN ({ROLES})", name="ck_research_gap_evidence_role"),
    )
    op.create_index("ix_research_gap_evidence_gap", "research_gap_evidence", ["gap_id"])


def downgrade() -> None:
    op.drop_table("research_gap_evidence")
    op.drop_table("research_gaps")
