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


MASTERY_STATES = (
    "NOT_ASSESSED",
    "INSUFFICIENT_EVIDENCE",
    "LEARNING",
    "DEVELOPING",
    "PROFICIENT",
    "STRONG",
)


class LearnerConceptState(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Current learner state for one concept (spec 13.4). Always derivable from `learner_evidence`
    and rebuilt by the mastery engine; `explanation` is structured so a result can be reproduced
    and tested."""

    __tablename__ = "learner_concept_states"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["workspaces.id", "workspaces.user_id"],
            ondelete="CASCADE",
            name="fk_learner_states_workspace_owner",
        ),
        ForeignKeyConstraint(
            ["knowledge_node_id", "workspace_id"],
            ["knowledge_nodes.id", "knowledge_nodes.workspace_id"],
            ondelete="CASCADE",
            name="fk_learner_states_node_workspace",
        ),
        CheckConstraint(f"state IN ({_sql(MASTERY_STATES)})", name="ck_learner_states_state"),
        CheckConstraint(
            "mastery_estimate IS NULL OR (mastery_estimate >= 0 AND mastery_estimate <= 1)",
            name="ck_learner_states_mastery",
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_learner_states_confidence"),
        CheckConstraint("evidence_count >= 0", name="ck_learner_states_count"),
        UniqueConstraint("user_id", "knowledge_node_id", name="uq_learner_states_user_node"),
        Index("ix_learner_states_user_state", "user_id", "state"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    knowledge_node_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # NULL while there is no evidence: an unassessed concept has no score, never a low one
    mastery_estimate: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    last_evidence_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    calculation_version: Mapped[str] = mapped_column(String(16), nullable=False)
    explanation: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )


MISCONCEPTION_STATUSES = ("suggested", "confirmed", "dismissed", "corrected")


class LearnerMisconception(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A recurring misunderstanding inferred from several wrong answers on one concept (spec 15).
    The model's output is untrusted: it is stored only after code has checked every cited answer and
    concept against the evidence that was actually sent. `description_key` makes detection
    retry-safe and keeps a dismissed misconception dismissed."""

    __tablename__ = "learner_misconceptions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["workspaces.id", "workspaces.user_id"],
            ondelete="CASCADE",
            name="fk_misconceptions_workspace_owner",
        ),
        ForeignKeyConstraint(
            ["knowledge_node_id", "workspace_id"],
            ["knowledge_nodes.id", "knowledge_nodes.workspace_id"],
            ondelete="CASCADE",
            name="fk_misconceptions_node_workspace",
        ),
        CheckConstraint(
            f"status IN ({_sql(MISCONCEPTION_STATUSES)})", name="ck_misconceptions_status"
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_misconceptions_confidence"),
        CheckConstraint("evidence_count >= 0", name="ck_misconceptions_count"),
        UniqueConstraint("id", "user_id", name="uq_misconceptions_id_user"),
        UniqueConstraint(
            "user_id", "knowledge_node_id", "description_key", name="uq_misconceptions_key"
        ),
        Index("ix_misconceptions_user_status", "user_id", "status"),
        Index("ix_misconceptions_node", "knowledge_node_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    knowledge_node_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_action: Mapped[str | None] = mapped_column(String(300), nullable=True)
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, server_default=text("'suggested'")
    )
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False)
    detection_version: Mapped[str] = mapped_column(String(16), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(40), nullable=False)
    model_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    description_key: Mapped[str] = mapped_column(String(64), nullable=False)
    related_node_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    edited_by_user: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LearnerMisconceptionEvidence(UUIDPrimaryKeyMixin, Base):
    """The wrong answers a misconception rests on. `source_event_id` is `quiz_attempt_answers.id`
    (no FK: the answer text is read live from the owner's data, never copied here)."""

    __tablename__ = "learner_misconception_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["misconception_id", "user_id"],
            ["learner_misconceptions.id", "learner_misconceptions.user_id"],
            ondelete="CASCADE",
            name="fk_misconception_evidence_owner",
        ),
        UniqueConstraint("misconception_id", "source_event_id", name="uq_misconception_event"),
        Index("ix_misconception_evidence_event", "user_id", "source_event_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    misconception_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)
    source_event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
