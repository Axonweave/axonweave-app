"""concept links and learner evidence (Phase 6 M6.5)

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "knowledge_concept_links",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("source_type", sa.String(length=16), nullable=False),
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("knowledge_node_id", sa.UUID(), nullable=False),
        sa.Column("method", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
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
            name="fk_concept_links_workspace_owner",
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_node_id", "workspace_id"],
            ["knowledge_nodes.id", "knowledge_nodes.workspace_id"],
            ondelete="CASCADE",
            name="fk_concept_links_node_workspace",
        ),
        sa.CheckConstraint(
            "source_type IN ('quiz_question', 'flashcard')", name="ck_concept_links_source_type"
        ),
        sa.CheckConstraint(
            "method IN ('exact_name', 'alias', 'source_reference', 'user')",
            name="ck_concept_links_method",
        ),
        sa.CheckConstraint(
            "status IN ('confirmed', 'proposed', 'rejected')", name="ck_concept_links_status"
        ),
        sa.UniqueConstraint(
            "user_id",
            "source_type",
            "source_id",
            "knowledge_node_id",
            name="uq_concept_links_source_node",
        ),
    )
    op.create_index(
        "ix_concept_links_source",
        "knowledge_concept_links",
        ["user_id", "source_type", "source_id"],
    )
    op.create_index(
        "ix_concept_links_node", "knowledge_concept_links", ["knowledge_node_id", "status"]
    )

    op.create_table(
        "learner_evidence",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("knowledge_node_id", sa.UUID(), nullable=True),
        sa.Column("source_type", sa.String(length=16), nullable=False),
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("source_event_id", sa.UUID(), nullable=False),
        sa.Column("topic", sa.String(length=120), nullable=True),
        sa.Column("evidence_value", sa.Numeric(4, 3), nullable=False),
        sa.Column(
            "evidence_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
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
            name="fk_learner_evidence_workspace_owner",
        ),
        sa.CheckConstraint(
            "source_type IN ('quiz_answer', 'flashcard_review')", name="ck_learner_evidence_source"
        ),
        sa.CheckConstraint(
            "evidence_value >= 0 AND evidence_value <= 1", name="ck_learner_evidence_value"
        ),
    )
    # SET NULL on one column of a composite key (PostgreSQL 15+), as in app.database.fk
    op.execute(
        "ALTER TABLE learner_evidence ADD CONSTRAINT fk_learner_evidence_node_workspace "
        "FOREIGN KEY (knowledge_node_id, workspace_id) "
        "REFERENCES knowledge_nodes (id, workspace_id) ON DELETE SET NULL (knowledge_node_id)"
    )
    op.create_index(
        "uq_learner_evidence_event_node",
        "learner_evidence",
        ["user_id", "source_type", "source_event_id", "knowledge_node_id"],
        unique=True,
        postgresql_where=sa.text("knowledge_node_id IS NOT NULL"),
    )
    op.create_index(
        "uq_learner_evidence_event_unmapped",
        "learner_evidence",
        ["user_id", "source_type", "source_event_id"],
        unique=True,
        postgresql_where=sa.text("knowledge_node_id IS NULL"),
    )
    op.create_index(
        "ix_learner_evidence_node_time",
        "learner_evidence",
        ["user_id", "knowledge_node_id", "occurred_at"],
    )
    op.create_index(
        "ix_learner_evidence_source", "learner_evidence", ["user_id", "source_type", "source_id"]
    )


def downgrade() -> None:
    op.drop_table("learner_evidence")
    op.drop_table("knowledge_concept_links")
