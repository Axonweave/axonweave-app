"""Phase 6 knowledge graph tables (D-122 to D-126).

The graph is plain PostgreSQL (D-125). Ownership is enforced in the database with composite foreign
keys on `(id, user_id)` and `(id, workspace_id)`: a node, an edge, an evidence row or a job can
never point at another user's workspace, document or node.

Evidence stores a short capped quote plus a hash and the document *version* and chunk *index*, not a
hard foreign key to a chunk, because reprocessing recreates chunks (D-123). `stale` marks evidence
whose version is no longer the active one.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.database.fk import SetNullColumnsFK

NODE_TYPES = (
    "concept",
    "topic",
    "subtopic",
    "term",
    "algorithm",
    "method",
    "formula",
    "model",
    "theory",
    "principle",
    "entity",
    "example",
    "application",
)
RELATIONSHIP_TYPES = (
    "IS_A",
    "PART_OF",
    "PREREQUISITE_OF",
    "DEPENDS_ON",
    "RELATED_TO",
    "CONTRASTS_WITH",
    "USES",
    "APPLIED_IN",
    "EXAMPLE_OF",
)
# Stored once with the smaller node id first, because direction carries no meaning.
SYMMETRIC_TYPES = ("RELATED_TO", "CONTRASTS_WITH")
EVIDENCE_TYPES = ("definition", "mention", "relationship_statement")
STATEMENT_KINDS = ("stated", "inferred")
ORIGINS = ("extracted", "user")

JOB_STATUSES = (
    "pending",
    "retrieving_sources",
    "extracting",
    "validating",
    "saving",
    "completed",
    "failed",
    "cancelled",
)
ACTIVE_JOB_STATUSES = ("pending", "retrieving_sources", "extracting", "validating", "saving")
CANDIDATE_STATUSES = ("open", "merged", "kept_separate", "related", "ignored")

QUOTE_MAX_CHARS = 300


def _sql(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


class KnowledgeNode(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_nodes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["workspaces.id", "workspaces.user_id"],
            ondelete="CASCADE",
            name="fk_knowledge_nodes_workspace_owner",
        ),
        SetNullColumnsFK(
            ["subject_id", "workspace_id"],
            ["subjects.id", "subjects.workspace_id"],
            set_null=["subject_id"],
            name="fk_knowledge_nodes_subject_workspace",
        ),
        UniqueConstraint("id", "user_id", name="uq_knowledge_nodes_id_user"),
        UniqueConstraint("id", "workspace_id", name="uq_knowledge_nodes_id_workspace"),
        CheckConstraint(f"node_type IN ({_sql(NODE_TYPES)})", name="ck_knowledge_nodes_type"),
        CheckConstraint(f"origin IN ({_sql(ORIGINS)})", name="ck_knowledge_nodes_origin"),
        CheckConstraint(
            "difficulty IS NULL OR difficulty IN ('introductory', 'intermediate', 'advanced')",
            name="ck_knowledge_nodes_difficulty",
        ),
        Index(
            "uq_knowledge_nodes_active_name",
            "user_id",
            "workspace_id",
            "normalised_name",
            "node_type",
            unique=True,
            postgresql_where=text("archived_at IS NULL"),
        ),
        Index("ix_knowledge_nodes_user_workspace", "user_id", "workspace_id"),
        Index("ix_knowledge_nodes_user_subject", "user_id", "subject_id"),
        Index("ix_knowledge_nodes_user_name", "user_id", "normalised_name"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    subject_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # The chapter must belong to the subject; the service checks it (a chapter has no workspace).
    chapter_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    normalised_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    definition: Mapped[str | None] = mapped_column(Text, nullable=True)
    node_type: Mapped[str] = mapped_column(String(24), nullable=False, default="concept")
    difficulty: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Not called `metadata`: that name is reserved on declarative models (assessment, section 1).
    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    origin: Mapped[str] = mapped_column(String(16), nullable=False, default="extracted")
    # Set when the user edits the node: re-extraction never overwrites it (spec 9.5, D-126).
    edited_by_user: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class KnowledgeNodeAlias(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "knowledge_node_aliases"
    __table_args__ = (
        ForeignKeyConstraint(
            ["knowledge_node_id", "user_id"],
            ["knowledge_nodes.id", "knowledge_nodes.user_id"],
            ondelete="CASCADE",
            name="fk_knowledge_aliases_node_owner",
        ),
        UniqueConstraint(
            "user_id",
            "workspace_id",
            "normalised_alias",
            name="uq_knowledge_aliases_workspace_alias",
        ),
        Index("ix_knowledge_aliases_node", "knowledge_node_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    knowledge_node_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    alias: Mapped[str] = mapped_column(String(200), nullable=False)
    normalised_alias: Mapped[str] = mapped_column(String(200), nullable=False)


class KnowledgeEdge(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_edges"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["workspaces.id", "workspaces.user_id"],
            ondelete="CASCADE",
            name="fk_knowledge_edges_workspace_owner",
        ),
        # Both ends must be nodes of the same workspace (so the same user): no cross-user edges.
        ForeignKeyConstraint(
            ["source_node_id", "workspace_id"],
            ["knowledge_nodes.id", "knowledge_nodes.workspace_id"],
            ondelete="CASCADE",
            name="fk_knowledge_edges_source_workspace",
        ),
        ForeignKeyConstraint(
            ["target_node_id", "workspace_id"],
            ["knowledge_nodes.id", "knowledge_nodes.workspace_id"],
            ondelete="CASCADE",
            name="fk_knowledge_edges_target_workspace",
        ),
        UniqueConstraint("id", "user_id", name="uq_knowledge_edges_id_user"),
        UniqueConstraint(
            "user_id",
            "source_node_id",
            "target_node_id",
            "relationship_type",
            name="uq_knowledge_edges_pair_type",
        ),
        CheckConstraint("source_node_id <> target_node_id", name="ck_knowledge_edges_no_self"),
        CheckConstraint(
            f"relationship_type IN ({_sql(RELATIONSHIP_TYPES)})", name="ck_knowledge_edges_type"
        ),
        CheckConstraint(
            f"statement_kind IN ({_sql(STATEMENT_KINDS)})", name="ck_knowledge_edges_kind"
        ),
        CheckConstraint(f"origin IN ({_sql(ORIGINS)})", name="ck_knowledge_edges_origin"),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_knowledge_edges_confidence",
        ),
        Index("ix_knowledge_edges_user_source", "user_id", "source_node_id"),
        Index("ix_knowledge_edges_user_target", "user_id", "target_node_id"),
        Index("ix_knowledge_edges_workspace", "workspace_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    source_node_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    target_node_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(24), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    statement_kind: Mapped[str] = mapped_column(String(12), nullable=False, default="stated")
    origin: Mapped[str] = mapped_column(String(16), nullable=False, default="extracted")


class KnowledgeExtractionJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One extraction run over one document. Mirrors `generation_jobs` (D-84 to D-87): the API only
    enqueues; the worker claims atomically; an identical active request returns the active job."""

    __tablename__ = "knowledge_extraction_jobs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["workspaces.id", "workspaces.user_id"],
            ondelete="CASCADE",
            name="fk_knowledge_jobs_workspace_owner",
        ),
        ForeignKeyConstraint(
            ["document_id", "user_id"],
            ["documents.id", "documents.user_id"],
            ondelete="CASCADE",
            name="fk_knowledge_jobs_document_owner",
        ),
        UniqueConstraint("id", "user_id", name="uq_knowledge_jobs_id_user"),
        CheckConstraint(f"status IN ({_sql(JOB_STATUSES)})", name="ck_knowledge_jobs_status"),
        CheckConstraint("progress >= 0 AND progress <= 100", name="ck_knowledge_jobs_progress"),
        CheckConstraint("provider_calls >= 0", name="ck_knowledge_jobs_provider_calls"),
        Index(
            "uq_knowledge_jobs_active_fingerprint",
            "user_id",
            "fingerprint",
            unique=True,
            postgresql_where=text(f"status IN ({_sql(ACTIVE_JOB_STATUSES)})"),
        ),
        Index("ix_knowledge_jobs_user_created", "user_id", "created_at"),
        Index("ix_knowledge_jobs_user_status", "user_id", "status"),
        Index("ix_knowledge_jobs_status_heartbeat", "status", "heartbeat_at"),
        Index("ix_knowledge_jobs_document", "document_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    document_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extraction_version: Mapped[str] = mapped_column(String(32), nullable=False)
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)  # safe code only
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    source_stats: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    result_stats: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    provider_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    celery_task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class KnowledgeEvidence(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "knowledge_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["workspaces.id", "workspaces.user_id"],
            ondelete="CASCADE",
            name="fk_knowledge_evidence_workspace_owner",
        ),
        ForeignKeyConstraint(
            ["knowledge_node_id", "user_id"],
            ["knowledge_nodes.id", "knowledge_nodes.user_id"],
            ondelete="CASCADE",
            name="fk_knowledge_evidence_node_owner",
        ),
        ForeignKeyConstraint(
            ["knowledge_edge_id", "user_id"],
            ["knowledge_edges.id", "knowledge_edges.user_id"],
            ondelete="CASCADE",
            name="fk_knowledge_evidence_edge_owner",
        ),
        ForeignKeyConstraint(
            ["document_id", "user_id"],
            ["documents.id", "documents.user_id"],
            ondelete="CASCADE",
            name="fk_knowledge_evidence_document_owner",
        ),
        ForeignKeyConstraint(
            ["document_version_id", "document_id"],
            ["document_versions.id", "document_versions.document_id"],
            ondelete="CASCADE",
            name="fk_knowledge_evidence_version_document",
        ),
        SetNullColumnsFK(
            ["extraction_job_id", "user_id"],
            ["knowledge_extraction_jobs.id", "knowledge_extraction_jobs.user_id"],
            set_null=["extraction_job_id"],
            name="fk_knowledge_evidence_job_owner",
        ),
        CheckConstraint(
            "knowledge_node_id IS NOT NULL OR knowledge_edge_id IS NOT NULL",
            name="ck_knowledge_evidence_target",
        ),
        CheckConstraint(
            f"evidence_type IN ({_sql(EVIDENCE_TYPES)})", name="ck_knowledge_evidence_type"
        ),
        CheckConstraint(
            f"char_length(quote) <= {QUOTE_MAX_CHARS}", name="ck_knowledge_evidence_quote"
        ),
        CheckConstraint("chunk_index >= 0", name="ck_knowledge_evidence_chunk_index"),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_knowledge_evidence_confidence",
        ),
        # A retry (or a re-run over the same version) never adds the same evidence twice.
        Index(
            "uq_knowledge_evidence_node_passage",
            "knowledge_node_id",
            "document_version_id",
            "chunk_index",
            "evidence_type",
            unique=True,
            postgresql_where=text("knowledge_edge_id IS NULL"),
        ),
        Index(
            "uq_knowledge_evidence_edge_passage",
            "knowledge_edge_id",
            "document_version_id",
            "chunk_index",
            unique=True,
            postgresql_where=text("knowledge_edge_id IS NOT NULL"),
        ),
        Index("ix_knowledge_evidence_node", "knowledge_node_id"),
        Index("ix_knowledge_evidence_edge", "knowledge_edge_id"),
        Index("ix_knowledge_evidence_user_document", "user_id", "document_id"),
        Index("ix_knowledge_evidence_version", "document_version_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    knowledge_node_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    knowledge_edge_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    document_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    slide_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quote: Mapped[str] = mapped_column(String(QUOTE_MAX_CHARS), nullable=False)
    quote_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(32), nullable=False)
    extraction_method: Mapped[str] = mapped_column(String(16), nullable=False, default="llm")
    extraction_job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    stale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class KnowledgeDuplicateCandidate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A reviewable "these may be the same concept" suggestion (spec 9.6). Never auto-merged."""

    __tablename__ = "knowledge_duplicate_candidates"
    __table_args__ = (
        ForeignKeyConstraint(
            ["node_a_id", "workspace_id"],
            ["knowledge_nodes.id", "knowledge_nodes.workspace_id"],
            ondelete="CASCADE",
            name="fk_knowledge_candidates_a_workspace",
        ),
        ForeignKeyConstraint(
            ["node_b_id", "workspace_id"],
            ["knowledge_nodes.id", "knowledge_nodes.workspace_id"],
            ondelete="CASCADE",
            name="fk_knowledge_candidates_b_workspace",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["workspaces.id", "workspaces.user_id"],
            ondelete="CASCADE",
            name="fk_knowledge_candidates_workspace_owner",
        ),
        # One row per unordered pair: the smaller id is always `node_a_id`.
        CheckConstraint("node_a_id < node_b_id", name="ck_knowledge_candidates_order"),
        CheckConstraint(
            f"status IN ({_sql(CANDIDATE_STATUSES)})", name="ck_knowledge_candidates_status"
        ),
        UniqueConstraint("user_id", "node_a_id", "node_b_id", name="uq_knowledge_candidates_pair"),
        Index("ix_knowledge_candidates_user_status", "user_id", "status"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    node_a_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    node_b_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # Which deterministic signals fired (normalised_name, alias, same_subject, ...). No text.
    signals: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")


class KnowledgeMergeHistory(UUIDPrimaryKeyMixin, Base):
    """Audit trail of merges (needed to explain a merge and to deduplicate learner evidence)."""

    __tablename__ = "knowledge_merge_history"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["workspaces.id", "workspaces.user_id"],
            ondelete="CASCADE",
            name="fk_knowledge_merge_workspace_owner",
        ),
        Index("ix_knowledge_merge_user_survivor", "user_id", "surviving_node_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # No foreign keys: the merged node no longer exists, and the survivor may be deleted later.
    surviving_node_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    merged_node_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    merged_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
