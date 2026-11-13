"""Phase 6 learner evidence tables (Milestone 6.5).

`knowledge_concept_links` maps a quiz question or flashcard to a concept. Only `confirmed` links
turn evidence into per-concept evidence; `proposed` links wait for review and `rejected` ones are
remembered so they are not proposed again (spec 13.2).

`learner_evidence` holds one canonical row per learner event (a graded quiz answer or a flashcard
review) and concept. Attempt-level aggregates are never ingested (spec 13.5). `knowledge_node_id`
is nullable: unmapped evidence stays available and is attached when a link is confirmed, and it is
kept (unmapped) if the concept is later deleted.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.database.fk import SetNullColumnsFK

LINK_SOURCE_TYPES = ("quiz_question", "flashcard")
LINK_METHODS = ("exact_name", "alias", "source_reference", "user")
LINK_STATUSES = ("confirmed", "proposed", "rejected")
EVIDENCE_SOURCE_TYPES = ("quiz_answer", "flashcard_review")


def _sql(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


class KnowledgeConceptLink(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_concept_links"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["workspaces.id", "workspaces.user_id"],
            ondelete="CASCADE",
            name="fk_concept_links_workspace_owner",
        ),
        ForeignKeyConstraint(
            ["knowledge_node_id", "workspace_id"],
            ["knowledge_nodes.id", "knowledge_nodes.workspace_id"],
            ondelete="CASCADE",
            name="fk_concept_links_node_workspace",
        ),
        CheckConstraint(
            f"source_type IN ({_sql(LINK_SOURCE_TYPES)})", name="ck_concept_links_source_type"
        ),
        CheckConstraint(f"method IN ({_sql(LINK_METHODS)})", name="ck_concept_links_method"),
        CheckConstraint(f"status IN ({_sql(LINK_STATUSES)})", name="ck_concept_links_status"),
        UniqueConstraint(
            "user_id",
            "source_type",
            "source_id",
            "knowledge_node_id",
            name="uq_concept_links_source_node",
        ),
        Index("ix_concept_links_source", "user_id", "source_type", "source_id"),
        Index("ix_concept_links_node", "knowledge_node_id", "status"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    knowledge_node_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    method: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False)


class LearnerEvidence(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "learner_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["workspaces.id", "workspaces.user_id"],
            ondelete="CASCADE",
            name="fk_learner_evidence_workspace_owner",
        ),
        SetNullColumnsFK(
            ["knowledge_node_id", "workspace_id"],
            ["knowledge_nodes.id", "knowledge_nodes.workspace_id"],
            set_null=["knowledge_node_id"],
            name="fk_learner_evidence_node_workspace",
        ),
        CheckConstraint(
            f"source_type IN ({_sql(EVIDENCE_SOURCE_TYPES)})", name="ck_learner_evidence_source"
        ),
        CheckConstraint(
            "evidence_value >= 0 AND evidence_value <= 1", name="ck_learner_evidence_value"
        ),
        # one row per event and concept; one unmapped row per event while it has no concept
        Index(
            "uq_learner_evidence_event_node",
            "user_id",
            "source_type",
            "source_event_id",
            "knowledge_node_id",
            unique=True,
            postgresql_where=text("knowledge_node_id IS NOT NULL"),
        ),
        Index(
            "uq_learner_evidence_event_unmapped",
            "user_id",
            "source_type",
            "source_event_id",
            unique=True,
            postgresql_where=text("knowledge_node_id IS NULL"),
        ),
        Index("ix_learner_evidence_node_time", "user_id", "knowledge_node_id", "occurred_at"),
        Index("ix_learner_evidence_source", "user_id", "source_type", "source_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    knowledge_node_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)
    # the question or card the event is about (no FK: the event stays traceable if it is deleted)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # the canonical event: quiz_attempt_answers.id or flashcard_reviews.id
    source_event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    topic: Mapped[str | None] = mapped_column(String(120), nullable=True)
    evidence_value: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    evidence_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
