"""knowledge duplicate candidates, merge history, 'extraction' usage kind (Phase 6 M6.1/M6.2)

Duplicate candidates are reviewable suggestions, never automatic merges (spec 9.6). Merge history
keeps an audit row per merge. Extraction calls record `request_kind = 'extraction'` and count toward
the daily token quota (D-124).

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATUSES = "'open', 'merged', 'kept_separate', 'related', 'ignored'"


def _ts(name: str) -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "knowledge_duplicate_candidates",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("node_a_id", sa.UUID(), nullable=False),
        sa.Column("node_b_id", sa.UUID(), nullable=False),
        sa.Column(
            "signals",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=16), server_default=sa.text("'open'"), nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["workspaces.id", "workspaces.user_id"],
            ondelete="CASCADE",
            name="fk_knowledge_candidates_workspace_owner",
        ),
        sa.ForeignKeyConstraint(
            ["node_a_id", "workspace_id"],
            ["knowledge_nodes.id", "knowledge_nodes.workspace_id"],
            ondelete="CASCADE",
            name="fk_knowledge_candidates_a_workspace",
        ),
        sa.ForeignKeyConstraint(
            ["node_b_id", "workspace_id"],
            ["knowledge_nodes.id", "knowledge_nodes.workspace_id"],
            ondelete="CASCADE",
            name="fk_knowledge_candidates_b_workspace",
        ),
        sa.CheckConstraint("node_a_id < node_b_id", name="ck_knowledge_candidates_order"),
        sa.CheckConstraint(f"status IN ({STATUSES})", name="ck_knowledge_candidates_status"),
        sa.UniqueConstraint(
            "user_id", "node_a_id", "node_b_id", name="uq_knowledge_candidates_pair"
        ),
    )
    op.create_index(
        op.f("ix_knowledge_duplicate_candidates_id"), "knowledge_duplicate_candidates", ["id"]
    )
    op.create_index(
        "ix_knowledge_candidates_user_status",
        "knowledge_duplicate_candidates",
        ["user_id", "status"],
    )

    op.create_table(
        "knowledge_merge_history",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("surviving_node_id", sa.UUID(), nullable=False),
        sa.Column("merged_node_id", sa.UUID(), nullable=False),
        sa.Column("merged_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        _ts("created_at"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["workspaces.id", "workspaces.user_id"],
            ondelete="CASCADE",
            name="fk_knowledge_merge_workspace_owner",
        ),
    )
    op.create_index(op.f("ix_knowledge_merge_history_id"), "knowledge_merge_history", ["id"])
    op.create_index(
        "ix_knowledge_merge_user_survivor",
        "knowledge_merge_history",
        ["user_id", "surviving_node_id"],
    )

    op.drop_constraint("ck_ai_usage_request_kind", "ai_usage_records", type_="check")
    op.create_check_constraint(
        "ck_ai_usage_request_kind",
        "ai_usage_records",
        "request_kind IN ('chat', 'embedding', 'generation', 'evaluation', 'extraction')",
    )


def downgrade() -> None:
    op.execute("DELETE FROM ai_usage_records WHERE request_kind = 'extraction'")
    op.drop_constraint("ck_ai_usage_request_kind", "ai_usage_records", type_="check")
    op.create_check_constraint(
        "ck_ai_usage_request_kind",
        "ai_usage_records",
        "request_kind IN ('chat', 'embedding', 'generation', 'evaluation')",
    )
    op.drop_table("knowledge_merge_history")
    op.drop_table("knowledge_duplicate_candidates")
