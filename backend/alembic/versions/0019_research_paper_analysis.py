"""paper analyses, evidence and notes, 'paper_analysis' usage kind (Phase 7 M7.3)

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_KINDS = "'chat', 'embedding', 'generation', 'evaluation', 'extraction', 'misconception'"
NEW_KINDS = OLD_KINDS + ", 'paper_analysis'"
STATUSES = (
    "'pending', 'retrieving_sources', 'extracting', 'validating', 'saving', "
    "'completed', 'failed', 'cancelled'"
)
ACTIVE = "'pending', 'retrieving_sources', 'extracting', 'validating', 'saving'"
SECTIONS = (
    "'research_problem', 'objectives', 'methodology', 'dataset', 'evaluation', 'results', "
    "'contributions', 'limitations', 'future_work', 'references'"
)


def _uuid(name: str, nullable: bool = False) -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=nullable)


def _ts(name: str) -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "research_paper_extractions",
        _uuid("id"),
        _uuid("user_id"),
        _uuid("research_paper_id"),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("extraction_version", sa.String(32), nullable=False),
        sa.Column("prompt_version", sa.String(64), nullable=True),
        sa.Column("model_identifier", sa.String(128), nullable=True),
        _uuid("document_id", nullable=True),
        _uuid("document_version_id", nullable=True),
        sa.Column("structured_result", postgresql.JSONB(), nullable=True),
        sa.Column("result_stats", postgresql.JSONB(), nullable=True),
        sa.Column("source_stats", postgresql.JSONB(), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False),
        sa.Column("provider_calls", sa.Integer(), nullable=False),
        sa.Column("celery_task_id", sa.String(64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["research_paper_id", "user_id"],
            ["research_papers.id", "research_papers.user_id"],
            name="fk_research_extractions_paper_owner",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("id", "user_id", name="uq_research_extractions_id_user"),
        sa.UniqueConstraint(
            "research_paper_id", "version_number", name="uq_research_extractions_ver"
        ),
        sa.CheckConstraint(f"status IN ({STATUSES})", name="ck_research_extractions_status"),
    )
    op.create_index(
        "uq_research_extractions_one_active",
        "research_paper_extractions",
        ["research_paper_id"],
        unique=True,
        postgresql_where=sa.text(f"status IN ({ACTIVE})"),
    )
    op.create_index(
        "ix_research_extractions_user_status", "research_paper_extractions", ["user_id", "status"]
    )

    op.create_table(
        "research_evidence",
        _uuid("id"),
        _uuid("user_id"),
        _uuid("research_project_id"),
        _uuid("research_paper_id"),
        _uuid("extraction_id"),
        sa.Column("claim_type", sa.String(24), nullable=False),
        sa.Column("claim_index", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(80), nullable=True),
        sa.Column("claim_text", sa.Text(), nullable=False),
        _uuid("document_id", nullable=True),
        _uuid("document_version_id", nullable=True),
        _uuid("chunk_id", nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("supporting_text", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("evidence_origin", sa.String(16), nullable=False),
        _ts("created_at"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["extraction_id", "user_id"],
            ["research_paper_extractions.id", "research_paper_extractions.user_id"],
            name="fk_research_evidence_extraction_owner",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["research_paper_id", "research_project_id"],
            ["research_papers.id", "research_papers.research_project_id"],
            name="fk_research_evidence_paper_project",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(f"claim_type IN ({SECTIONS})", name="ck_research_evidence_type"),
        sa.CheckConstraint(
            "evidence_origin IN ('reported', 'ai_inferred')", name="ck_research_evidence_origin"
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_research_evidence_confidence",
        ),
    )
    op.create_index(
        "ix_research_evidence_extraction",
        "research_evidence",
        ["extraction_id", "claim_type", "claim_index"],
    )
    op.create_index(
        "ix_research_evidence_paper", "research_evidence", ["user_id", "research_paper_id"]
    )

    op.create_table(
        "research_paper_notes",
        _uuid("id"),
        _uuid("user_id"),
        _uuid("research_paper_id"),
        sa.Column("section", sa.String(24), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["research_paper_id", "user_id"],
            ["research_papers.id", "research_papers.user_id"],
            name="fk_research_notes_paper_owner",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            f"section IS NULL OR section IN ({SECTIONS})", name="ck_research_notes_section"
        ),
    )
    op.create_index(
        "ix_research_notes_paper", "research_paper_notes", ["user_id", "research_paper_id"]
    )

    op.drop_constraint("ck_ai_usage_request_kind", "ai_usage_records", type_="check")
    op.create_check_constraint(
        "ck_ai_usage_request_kind", "ai_usage_records", f"request_kind IN ({NEW_KINDS})"
    )


def downgrade() -> None:
    op.execute("DELETE FROM ai_usage_records WHERE request_kind = 'paper_analysis'")
    op.drop_constraint("ck_ai_usage_request_kind", "ai_usage_records", type_="check")
    op.create_check_constraint(
        "ck_ai_usage_request_kind", "ai_usage_records", f"request_kind IN ({OLD_KINDS})"
    )
    op.drop_table("research_paper_notes")
    op.drop_table("research_evidence")
    op.drop_table("research_paper_extractions")
