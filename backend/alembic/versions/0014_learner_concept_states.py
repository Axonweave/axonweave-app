"""learner concept states (Phase 6 M6.6)

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATES = "'NOT_ASSESSED', 'INSUFFICIENT_EVIDENCE', 'LEARNING', 'DEVELOPING', 'PROFICIENT', 'STRONG'"


def _ts(name: str) -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "learner_concept_states",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("knowledge_node_id", sa.UUID(), nullable=False),
        sa.Column("mastery_estimate", sa.Numeric(4, 3), nullable=True),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False),
        sa.Column("evidence_count", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=24), nullable=False),
        sa.Column("last_evidence_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_review_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("calculation_version", sa.String(length=16), nullable=False),
        sa.Column(
            "explanation",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["workspaces.id", "workspaces.user_id"],
            ondelete="CASCADE",
            name="fk_learner_states_workspace_owner",
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_node_id", "workspace_id"],
            ["knowledge_nodes.id", "knowledge_nodes.workspace_id"],
            ondelete="CASCADE",
            name="fk_learner_states_node_workspace",
        ),
        sa.CheckConstraint(f"state IN ({STATES})", name="ck_learner_states_state"),
        sa.CheckConstraint(
            "mastery_estimate IS NULL OR (mastery_estimate >= 0 AND mastery_estimate <= 1)",
            name="ck_learner_states_mastery",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_learner_states_confidence"
        ),
        sa.CheckConstraint("evidence_count >= 0", name="ck_learner_states_count"),
        sa.UniqueConstraint("user_id", "knowledge_node_id", name="uq_learner_states_user_node"),
    )
    op.create_index("ix_learner_states_user_state", "learner_concept_states", ["user_id", "state"])


def downgrade() -> None:
    op.drop_table("learner_concept_states")
