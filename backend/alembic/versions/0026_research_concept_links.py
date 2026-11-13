"""research concept links (Phase 7 M7.10)

Revision ID: 0026
Revises: 0025
Create Date: 2026-11-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "research_concept_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("research_project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("research_paper_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("knowledge_node_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("match_kind", sa.String(8), nullable=False),
        sa.Column("matched_text", sa.String(200), nullable=False),
        sa.Column("link_status", sa.String(12), nullable=False),
        sa.Column("extraction_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("research_evidence_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("claim_type", sa.String(24), nullable=False),
        sa.Column("claim_text", sa.Text(), nullable=False),
        sa.Column("mention_count", sa.Integer(), nullable=False),
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
            name="fk_research_concept_links_project_owner",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["research_paper_id", "user_id"],
            ["research_papers.id", "research_papers.user_id"],
            name="fk_research_concept_links_paper_owner",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_node_id", "user_id"],
            ["knowledge_nodes.id", "knowledge_nodes.user_id"],
            name="fk_research_concept_links_node_owner",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["extraction_id"], ["research_paper_extractions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["research_evidence_id"], ["research_evidence.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint(
            "user_id", "research_paper_id", "knowledge_node_id", name="uq_research_concept_links"
        ),
        sa.CheckConstraint(
            "link_status IN ('suggested', 'confirmed', 'rejected')",
            name="ck_research_concept_links_status",
        ),
        sa.CheckConstraint(
            "match_kind IN ('name', 'alias')", name="ck_research_concept_links_match"
        ),
    )
    op.create_index(
        "ix_research_concept_links_node",
        "research_concept_links",
        ["user_id", "knowledge_node_id", "link_status"],
    )
    op.create_index(
        "ix_research_concept_links_project",
        "research_concept_links",
        ["user_id", "research_project_id"],
    )


def downgrade() -> None:
    op.drop_table("research_concept_links")
