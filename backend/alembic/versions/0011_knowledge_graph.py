"""knowledge graph: nodes, aliases, edges, extraction jobs, evidence (Phase 6 M6.1/M6.2, D-122 to D-126)

Plain PostgreSQL tables. Ownership is enforced with composite foreign keys on (id, user_id) and
(id, workspace_id), so no row can reference another user's workspace, document or node.

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NODE_TYPES = (
    "'concept', 'topic', 'subtopic', 'term', 'algorithm', 'method', 'formula', 'model', "
    "'theory', 'principle', 'entity', 'example', 'application'"
)
REL_TYPES = (
    "'IS_A', 'PART_OF', 'PREREQUISITE_OF', 'DEPENDS_ON', 'RELATED_TO', 'CONTRASTS_WITH', "
    "'USES', 'APPLIED_IN', 'EXAMPLE_OF'"
)
JOB_STATUSES = (
    "'pending', 'retrieving_sources', 'extracting', 'validating', 'saving', "
    "'completed', 'failed', 'cancelled'"
)
ACTIVE = "'pending', 'retrieving_sources', 'extracting', 'validating', 'saving'"


def _ts(name: str) -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def _user_fk() -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE")


def _workspace_fk(name: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["workspace_id", "user_id"],
        ["workspaces.id", "workspaces.user_id"],
        ondelete="CASCADE",
        name=name,
    )


def upgrade() -> None:
    # ── knowledge_nodes ──────────────────────────────────────────────────────
    op.create_table(
        "knowledge_nodes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("subject_id", sa.UUID(), nullable=True),
        sa.Column("chapter_id", sa.UUID(), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("normalised_name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("definition", sa.Text(), nullable=True),
        sa.Column(
            "node_type", sa.String(length=24), server_default=sa.text("'concept'"), nullable=False
        ),
        sa.Column("difficulty", sa.String(length=16), nullable=True),
        sa.Column(
            "attributes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "origin", sa.String(length=16), server_default=sa.text("'extracted'"), nullable=False
        ),
        sa.Column("edited_by_user", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id"),
        _user_fk(),
        _workspace_fk("fk_knowledge_nodes_workspace_owner"),
        sa.ForeignKeyConstraint(["chapter_id"], ["chapters.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("id", "user_id", name="uq_knowledge_nodes_id_user"),
        sa.UniqueConstraint("id", "workspace_id", name="uq_knowledge_nodes_id_workspace"),
        sa.CheckConstraint(f"node_type IN ({NODE_TYPES})", name="ck_knowledge_nodes_type"),
        sa.CheckConstraint("origin IN ('extracted', 'user')", name="ck_knowledge_nodes_origin"),
        sa.CheckConstraint(
            "difficulty IS NULL OR difficulty IN ('introductory', 'intermediate', 'advanced')",
            name="ck_knowledge_nodes_difficulty",
        ),
    )
    # The subject link is cleared (not cascaded) when the subject goes; the owner column is kept.
    op.execute(
        "ALTER TABLE knowledge_nodes ADD CONSTRAINT fk_knowledge_nodes_subject_workspace "
        "FOREIGN KEY (subject_id, workspace_id) REFERENCES subjects (id, workspace_id) "
        "ON DELETE SET NULL (subject_id)"
    )
    op.create_index(op.f("ix_knowledge_nodes_id"), "knowledge_nodes", ["id"])
    op.create_index(
        "uq_knowledge_nodes_active_name",
        "knowledge_nodes",
        ["user_id", "workspace_id", "normalised_name", "node_type"],
        unique=True,
        postgresql_where=sa.text("archived_at IS NULL"),
    )
    op.create_index(
        "ix_knowledge_nodes_user_workspace", "knowledge_nodes", ["user_id", "workspace_id"]
    )
    op.create_index("ix_knowledge_nodes_user_subject", "knowledge_nodes", ["user_id", "subject_id"])
    op.create_index(
        "ix_knowledge_nodes_user_name", "knowledge_nodes", ["user_id", "normalised_name"]
    )

    # ── knowledge_node_aliases ───────────────────────────────────────────────
    op.create_table(
        "knowledge_node_aliases",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("knowledge_node_id", sa.UUID(), nullable=False),
        sa.Column("alias", sa.String(length=200), nullable=False),
        sa.Column("normalised_alias", sa.String(length=200), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        _user_fk(),
        sa.ForeignKeyConstraint(
            ["knowledge_node_id", "user_id"],
            ["knowledge_nodes.id", "knowledge_nodes.user_id"],
            ondelete="CASCADE",
            name="fk_knowledge_aliases_node_owner",
        ),
        sa.UniqueConstraint(
            "user_id",
            "workspace_id",
            "normalised_alias",
            name="uq_knowledge_aliases_workspace_alias",
        ),
    )
    op.create_index(op.f("ix_knowledge_node_aliases_id"), "knowledge_node_aliases", ["id"])
    op.create_index("ix_knowledge_aliases_node", "knowledge_node_aliases", ["knowledge_node_id"])

    # ── knowledge_edges ──────────────────────────────────────────────────────
    op.create_table(
        "knowledge_edges",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("source_node_id", sa.UUID(), nullable=False),
        sa.Column("target_node_id", sa.UUID(), nullable=False),
        sa.Column("relationship_type", sa.String(length=24), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column(
            "statement_kind",
            sa.String(length=12),
            server_default=sa.text("'stated'"),
            nullable=False,
        ),
        sa.Column(
            "origin", sa.String(length=16), server_default=sa.text("'extracted'"), nullable=False
        ),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id"),
        _user_fk(),
        _workspace_fk("fk_knowledge_edges_workspace_owner"),
        sa.ForeignKeyConstraint(
            ["source_node_id", "workspace_id"],
            ["knowledge_nodes.id", "knowledge_nodes.workspace_id"],
            ondelete="CASCADE",
            name="fk_knowledge_edges_source_workspace",
        ),
        sa.ForeignKeyConstraint(
            ["target_node_id", "workspace_id"],
            ["knowledge_nodes.id", "knowledge_nodes.workspace_id"],
            ondelete="CASCADE",
            name="fk_knowledge_edges_target_workspace",
        ),
        sa.UniqueConstraint("id", "user_id", name="uq_knowledge_edges_id_user"),
        sa.UniqueConstraint(
            "user_id",
            "source_node_id",
            "target_node_id",
            "relationship_type",
            name="uq_knowledge_edges_pair_type",
        ),
        sa.CheckConstraint("source_node_id <> target_node_id", name="ck_knowledge_edges_no_self"),
        sa.CheckConstraint(f"relationship_type IN ({REL_TYPES})", name="ck_knowledge_edges_type"),
        sa.CheckConstraint(
            "statement_kind IN ('stated', 'inferred')", name="ck_knowledge_edges_kind"
        ),
        sa.CheckConstraint("origin IN ('extracted', 'user')", name="ck_knowledge_edges_origin"),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_knowledge_edges_confidence",
        ),
    )
    op.create_index(op.f("ix_knowledge_edges_id"), "knowledge_edges", ["id"])
    op.create_index(
        "ix_knowledge_edges_user_source", "knowledge_edges", ["user_id", "source_node_id"]
    )
    op.create_index(
        "ix_knowledge_edges_user_target", "knowledge_edges", ["user_id", "target_node_id"]
    )
    op.create_index("ix_knowledge_edges_workspace", "knowledge_edges", ["workspace_id"])

    # ── knowledge_extraction_jobs ────────────────────────────────────────────
    op.create_table(
        "knowledge_extraction_jobs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("document_version_id", sa.UUID(), nullable=True),
        sa.Column(
            "status", sa.String(length=24), server_default=sa.text("'pending'"), nullable=False
        ),
        sa.Column("progress", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("extraction_version", sa.String(length=32), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=True),
        sa.Column("model_id", sa.String(length=128), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("source_stats", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("result_stats", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("provider_calls", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "cancel_requested", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("celery_task_id", sa.String(length=64), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id"),
        _user_fk(),
        _workspace_fk("fk_knowledge_jobs_workspace_owner"),
        sa.ForeignKeyConstraint(
            ["document_id", "user_id"],
            ["documents.id", "documents.user_id"],
            ondelete="CASCADE",
            name="fk_knowledge_jobs_document_owner",
        ),
        sa.UniqueConstraint("id", "user_id", name="uq_knowledge_jobs_id_user"),
        sa.CheckConstraint(f"status IN ({JOB_STATUSES})", name="ck_knowledge_jobs_status"),
        sa.CheckConstraint("progress >= 0 AND progress <= 100", name="ck_knowledge_jobs_progress"),
        sa.CheckConstraint("provider_calls >= 0", name="ck_knowledge_jobs_provider_calls"),
    )
    op.create_index(op.f("ix_knowledge_extraction_jobs_id"), "knowledge_extraction_jobs", ["id"])
    op.create_index(
        "uq_knowledge_jobs_active_fingerprint",
        "knowledge_extraction_jobs",
        ["user_id", "fingerprint"],
        unique=True,
        postgresql_where=sa.text(f"status IN ({ACTIVE})"),
    )
    op.create_index(
        "ix_knowledge_jobs_user_created", "knowledge_extraction_jobs", ["user_id", "created_at"]
    )
    op.create_index(
        "ix_knowledge_jobs_user_status", "knowledge_extraction_jobs", ["user_id", "status"]
    )
    op.create_index(
        "ix_knowledge_jobs_status_heartbeat",
        "knowledge_extraction_jobs",
        ["status", "heartbeat_at"],
    )
    op.create_index("ix_knowledge_jobs_document", "knowledge_extraction_jobs", ["document_id"])

    # ── knowledge_evidence ───────────────────────────────────────────────────
    op.create_table(
        "knowledge_evidence",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("knowledge_node_id", sa.UUID(), nullable=True),
        sa.Column("knowledge_edge_id", sa.UUID(), nullable=True),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("document_version_id", sa.UUID(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("chunk_id", sa.UUID(), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("slide_number", sa.Integer(), nullable=True),
        sa.Column("quote", sa.String(length=300), nullable=False),
        sa.Column("quote_hash", sa.String(length=64), nullable=False),
        sa.Column("evidence_type", sa.String(length=32), nullable=False),
        sa.Column(
            "extraction_method",
            sa.String(length=16),
            server_default=sa.text("'llm'"),
            nullable=False,
        ),
        sa.Column("extraction_job_id", sa.UUID(), nullable=True),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column("stale", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        _ts("created_at"),
        sa.PrimaryKeyConstraint("id"),
        _user_fk(),
        _workspace_fk("fk_knowledge_evidence_workspace_owner"),
        sa.ForeignKeyConstraint(
            ["knowledge_node_id", "user_id"],
            ["knowledge_nodes.id", "knowledge_nodes.user_id"],
            ondelete="CASCADE",
            name="fk_knowledge_evidence_node_owner",
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_edge_id", "user_id"],
            ["knowledge_edges.id", "knowledge_edges.user_id"],
            ondelete="CASCADE",
            name="fk_knowledge_evidence_edge_owner",
        ),
        sa.ForeignKeyConstraint(
            ["document_id", "user_id"],
            ["documents.id", "documents.user_id"],
            ondelete="CASCADE",
            name="fk_knowledge_evidence_document_owner",
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id", "document_id"],
            ["document_versions.id", "document_versions.document_id"],
            ondelete="CASCADE",
            name="fk_knowledge_evidence_version_document",
        ),
        sa.CheckConstraint(
            "knowledge_node_id IS NOT NULL OR knowledge_edge_id IS NOT NULL",
            name="ck_knowledge_evidence_target",
        ),
        sa.CheckConstraint(
            "evidence_type IN ('definition', 'mention', 'relationship_statement')",
            name="ck_knowledge_evidence_type",
        ),
        sa.CheckConstraint("char_length(quote) <= 300", name="ck_knowledge_evidence_quote"),
        sa.CheckConstraint("chunk_index >= 0", name="ck_knowledge_evidence_chunk_index"),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_knowledge_evidence_confidence",
        ),
    )
    op.execute(
        "ALTER TABLE knowledge_evidence ADD CONSTRAINT fk_knowledge_evidence_job_owner "
        "FOREIGN KEY (extraction_job_id, user_id) "
        "REFERENCES knowledge_extraction_jobs (id, user_id) "
        "ON DELETE SET NULL (extraction_job_id)"
    )
    op.create_index(op.f("ix_knowledge_evidence_id"), "knowledge_evidence", ["id"])
    op.create_index(
        "uq_knowledge_evidence_node_passage",
        "knowledge_evidence",
        ["knowledge_node_id", "document_version_id", "chunk_index", "evidence_type"],
        unique=True,
        postgresql_where=sa.text("knowledge_edge_id IS NULL"),
    )
    op.create_index(
        "uq_knowledge_evidence_edge_passage",
        "knowledge_evidence",
        ["knowledge_edge_id", "document_version_id", "chunk_index"],
        unique=True,
        postgresql_where=sa.text("knowledge_edge_id IS NOT NULL"),
    )
    op.create_index("ix_knowledge_evidence_node", "knowledge_evidence", ["knowledge_node_id"])
    op.create_index("ix_knowledge_evidence_edge", "knowledge_evidence", ["knowledge_edge_id"])
    op.create_index(
        "ix_knowledge_evidence_user_document", "knowledge_evidence", ["user_id", "document_id"]
    )
    op.create_index("ix_knowledge_evidence_version", "knowledge_evidence", ["document_version_id"])


def downgrade() -> None:
    op.drop_table("knowledge_evidence")
    op.drop_table("knowledge_extraction_jobs")
    op.drop_table("knowledge_edges")
    op.drop_table("knowledge_node_aliases")
    op.drop_table("knowledge_nodes")
