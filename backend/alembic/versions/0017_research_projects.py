"""research projects (Phase 7 M7.1)

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATUSES = "'planning', 'active', 'on_hold', 'completed'"


def _list_col(name: str) -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(
        name, postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "research_projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("domain", sa.String(120), nullable=True),
        sa.Column("research_problem", sa.Text(), nullable=True),
        _list_col("objectives"),
        _list_col("research_questions"),
        _list_col("keywords"),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
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
            ["workspace_id", "user_id"],
            ["workspaces.id", "workspaces.user_id"],
            ondelete="CASCADE",
            name="fk_research_projects_workspace_owner",
        ),
        sa.UniqueConstraint("id", "user_id", name="uq_research_projects_id_user"),
        sa.UniqueConstraint("id", "workspace_id", name="uq_research_projects_id_workspace"),
        sa.CheckConstraint(f"status IN ({STATUSES})", name="ck_research_projects_status"),
        sa.CheckConstraint(
            "target_date IS NULL OR start_date IS NULL OR target_date >= start_date",
            name="ck_research_projects_dates",
        ),
    )
    op.create_index(
        "ix_research_projects_user_workspace", "research_projects", ["user_id", "workspace_id"]
    )
    op.create_index("ix_research_projects_user_status", "research_projects", ["user_id", "status"])
    op.create_index(
        "ix_research_projects_user_updated", "research_projects", ["user_id", "updated_at"]
    )


def downgrade() -> None:
    op.drop_table("research_projects")
