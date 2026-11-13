"""research drafts and versions, 'research_writing' usage kind (Phase 7 M7.9)

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_KINDS = (
    "'chat', 'embedding', 'generation', 'evaluation', 'extraction', 'misconception', "
    "'paper_analysis'"
)
NEW_KINDS = OLD_KINDS + ", 'research_writing'"
TYPES = "'research_paper', 'literature_review', 'proposal', 'report', 'notes'"
STATUSES = "'draft', 'in_review', 'final'"
STYLES = "'apa', 'ieee', 'mla', 'chicago', 'harvard'"
SOURCES = "'created', 'manual', 'ai_suggestion', 'restore'"


def upgrade() -> None:
    op.create_table(
        "research_drafts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("research_project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("document_type", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("citation_style", sa.String(12), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
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
            name="fk_research_drafts_project_owner",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("id", "user_id", name="uq_research_drafts_id_user"),
        sa.CheckConstraint(f"document_type IN ({TYPES})", name="ck_research_drafts_type"),
        sa.CheckConstraint(f"status IN ({STATUSES})", name="ck_research_drafts_status"),
        sa.CheckConstraint(f"citation_style IN ({STYLES})", name="ck_research_drafts_style"),
    )
    op.create_index(
        "ix_research_drafts_project",
        "research_drafts",
        ["user_id", "research_project_id", "updated_at"],
    )
    op.create_table(
        "research_draft_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("draft_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("title_snapshot", sa.String(200), nullable=False),
        sa.Column("content_snapshot", sa.Text(), nullable=False),
        sa.Column("change_summary", sa.String(300), nullable=False),
        sa.Column("change_source", sa.String(14), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["draft_id", "user_id"],
            ["research_drafts.id", "research_drafts.user_id"],
            name="fk_research_draft_versions_draft_owner",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("draft_id", "version_number", name="uq_research_draft_versions_number"),
        sa.CheckConstraint(
            f"change_source IN ({SOURCES})", name="ck_research_draft_versions_source"
        ),
    )
    op.drop_constraint("ck_ai_usage_request_kind", "ai_usage_records", type_="check")
    op.create_check_constraint(
        "ck_ai_usage_request_kind", "ai_usage_records", f"request_kind IN ({NEW_KINDS})"
    )


def downgrade() -> None:
    op.execute("DELETE FROM ai_usage_records WHERE request_kind = 'research_writing'")
    op.drop_constraint("ck_ai_usage_request_kind", "ai_usage_records", type_="check")
    op.create_check_constraint(
        "ck_ai_usage_request_kind", "ai_usage_records", f"request_kind IN ({OLD_KINDS})"
    )
    op.drop_table("research_draft_versions")
    op.drop_table("research_drafts")
