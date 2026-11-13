"""learner misconceptions and 'misconception' usage kind (Phase 6 M6.7)

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_KINDS = "'chat', 'embedding', 'generation', 'evaluation', 'extraction'"
NEW_KINDS = OLD_KINDS + ", 'misconception'"


def _ts(name: str) -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "learner_misconceptions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("knowledge_node_id", sa.UUID(), nullable=False),
        sa.Column("description", sa.String(length=300), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("recommended_action", sa.String(length=300), nullable=True),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False),
        sa.Column(
            "status", sa.String(length=12), server_default=sa.text("'suggested'"), nullable=False
        ),
        sa.Column("evidence_count", sa.Integer(), nullable=False),
        sa.Column("detection_version", sa.String(length=16), nullable=False),
        sa.Column("prompt_version", sa.String(length=40), nullable=False),
        sa.Column("model_id", sa.String(length=100), nullable=True),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("description_key", sa.String(length=64), nullable=False),
        sa.Column(
            "related_node_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("edited_by_user", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["workspaces.id", "workspaces.user_id"],
            ondelete="CASCADE",
            name="fk_misconceptions_workspace_owner",
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_node_id", "workspace_id"],
            ["knowledge_nodes.id", "knowledge_nodes.workspace_id"],
            ondelete="CASCADE",
            name="fk_misconceptions_node_workspace",
        ),
        sa.CheckConstraint(
            "status IN ('suggested', 'confirmed', 'dismissed', 'corrected')",
            name="ck_misconceptions_status",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_misconceptions_confidence"
        ),
        sa.CheckConstraint("evidence_count >= 0", name="ck_misconceptions_count"),
        sa.UniqueConstraint("id", "user_id", name="uq_misconceptions_id_user"),
        sa.UniqueConstraint(
            "user_id", "knowledge_node_id", "description_key", name="uq_misconceptions_key"
        ),
    )
    op.create_index(
        "ix_misconceptions_user_status", "learner_misconceptions", ["user_id", "status"]
    )
    op.create_index("ix_misconceptions_node", "learner_misconceptions", ["knowledge_node_id"])

    op.create_table(
        "learner_misconception_evidence",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("misconception_id", sa.UUID(), nullable=False),
        sa.Column("source_type", sa.String(length=16), nullable=False),
        sa.Column("source_event_id", sa.UUID(), nullable=False),
        sa.Column("source_id", sa.UUID(), nullable=False),
        _ts("created_at"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["misconception_id", "user_id"],
            ["learner_misconceptions.id", "learner_misconceptions.user_id"],
            ondelete="CASCADE",
            name="fk_misconception_evidence_owner",
        ),
        sa.UniqueConstraint("misconception_id", "source_event_id", name="uq_misconception_event"),
    )
    op.create_index(
        "ix_misconception_evidence_event",
        "learner_misconception_evidence",
        ["user_id", "source_event_id"],
    )

    op.drop_constraint("ck_ai_usage_request_kind", "ai_usage_records", type_="check")
    op.create_check_constraint(
        "ck_ai_usage_request_kind", "ai_usage_records", f"request_kind IN ({NEW_KINDS})"
    )


def downgrade() -> None:
    op.execute("DELETE FROM ai_usage_records WHERE request_kind = 'misconception'")
    op.drop_constraint("ck_ai_usage_request_kind", "ai_usage_records", type_="check")
    op.create_check_constraint(
        "ck_ai_usage_request_kind", "ai_usage_records", f"request_kind IN ({OLD_KINDS})"
    )
    op.drop_table("learner_misconception_evidence")
    op.drop_table("learner_misconceptions")
