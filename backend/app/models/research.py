"""Research Studio tables (Phase 7). Milestone 7.1: research projects.

A project lives in one of the user's workspaces (composite foreign key, so a project can never point
at someone else's workspace). Later milestones hang papers, notes, matrices and drafts off the
`(id, user_id)` and `(id, workspace_id)` keys declared here."""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.database.fk import SetNullColumnsFK

PROJECT_STATUSES = ("planning", "active", "on_hold", "completed")
_STATUS_SQL = ", ".join(f"'{s}'" for s in PROJECT_STATUSES)


class ResearchProject(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "research_projects"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["workspaces.id", "workspaces.user_id"],
            ondelete="CASCADE",
            name="fk_research_projects_workspace_owner",
        ),
        UniqueConstraint("id", "user_id", name="uq_research_projects_id_user"),
        UniqueConstraint("id", "workspace_id", name="uq_research_projects_id_workspace"),
        CheckConstraint(f"status IN ({_STATUS_SQL})", name="ck_research_projects_status"),
        CheckConstraint(
            "target_date IS NULL OR start_date IS NULL OR target_date >= start_date",
            name="ck_research_projects_dates",
        ),
        Index("ix_research_projects_user_workspace", "user_id", "workspace_id"),
        Index("ix_research_projects_user_status", "user_id", "status"),
        Index("ix_research_projects_user_updated", "user_id", "updated_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    domain: Mapped[str | None] = mapped_column(String(120), nullable=True)
    research_problem: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Short ordered lists the user edits as a whole; no independent lifecycle (spec 23.3).
    objectives: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    research_questions: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    keywords: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="planning")
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


PAPER_SOURCES = ("user_supplied", "pdf_extracted", "external_provider")
PAPER_STATUSES = ("unread", "reading", "read")
ANALYSIS_STATUSES = ("not_analysed", "queued", "analysing", "analysed", "failed")


def _sql(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


class ResearchPaper(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A paper in a research project (Phase 7 M7.2). The record can exist without a file (manual or
    DOI entry); a linked document goes through the ordinary Phase 3 ingestion. `doi` is stored in
    normalised form so the per-project uniqueness check is exact."""

    __tablename__ = "research_papers"
    __table_args__ = (
        ForeignKeyConstraint(
            ["research_project_id", "user_id"],
            ["research_projects.id", "research_projects.user_id"],
            ondelete="CASCADE",
            name="fk_research_papers_project_owner",
        ),
        # A deleted document must not delete the paper record: only the link is cleared.
        SetNullColumnsFK(
            ["document_id", "user_id"],
            ["documents.id", "documents.user_id"],
            set_null=["document_id"],
            name="fk_research_papers_document_owner",
        ),
        UniqueConstraint("id", "user_id", name="uq_research_papers_id_user"),
        UniqueConstraint("id", "research_project_id", name="uq_research_papers_id_project"),
        CheckConstraint(
            f"metadata_source IN ({_sql(PAPER_SOURCES)})", name="ck_research_papers_source"
        ),
        CheckConstraint(f"status IN ({_sql(PAPER_STATUSES)})", name="ck_research_papers_status"),
        CheckConstraint(
            f"analysis_status IN ({_sql(ANALYSIS_STATUSES)})", name="ck_research_papers_analysis"
        ),
        CheckConstraint(
            "publication_year IS NULL OR (publication_year >= 1000 AND publication_year <= 2200)",
            name="ck_research_papers_year",
        ),
        Index(
            "uq_research_papers_project_doi",
            "research_project_id",
            "doi",
            unique=True,
            postgresql_where=text("doi IS NOT NULL"),
        ),
        Index(
            "uq_research_papers_project_document",
            "research_project_id",
            "document_id",
            unique=True,
            postgresql_where=text("document_id IS NOT NULL"),
        ),
        Index("ix_research_papers_user_project", "user_id", "research_project_id"),
        Index("ix_research_papers_project_title", "research_project_id", "title_normalised"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    research_project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    title_normalised: Mapped[str] = mapped_column(String(500), nullable=False)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    authors: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    publication_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    venue: Mapped[str | None] = mapped_column(String(300), nullable=True)
    publisher: Mapped[str | None] = mapped_column(String(200), nullable=True)
    doi: Mapped[str | None] = mapped_column(String(200), nullable=True)
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    keywords: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    volume: Mapped[str | None] = mapped_column(String(40), nullable=True)
    issue: Mapped[str | None] = mapped_column(String(40), nullable=True)
    pages: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # Where the metadata came from (provenance) and whether the user has checked it.
    metadata_source: Mapped[str] = mapped_column(
        String(24), nullable=False, default="user_supplied"
    )
    metadata_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="unread")
    analysis_status: Mapped[str] = mapped_column(String(24), nullable=False, default="not_analysed")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ResearchPaperDuplicateReview(UUIDPrimaryKeyMixin, Base):
    """The user's decision that two papers are different works, so the pair stops being suggested.
    `paper_a_id` sorts before `paper_b_id`."""

    __tablename__ = "research_paper_duplicate_reviews"
    __table_args__ = (
        ForeignKeyConstraint(
            ["paper_a_id", "user_id"],
            ["research_papers.id", "research_papers.user_id"],
            ondelete="CASCADE",
            name="fk_research_dup_a_owner",
        ),
        ForeignKeyConstraint(
            ["paper_b_id", "user_id"],
            ["research_papers.id", "research_papers.user_id"],
            ondelete="CASCADE",
            name="fk_research_dup_b_owner",
        ),
        UniqueConstraint("paper_a_id", "paper_b_id", name="uq_research_dup_pair"),
        CheckConstraint("paper_a_id < paper_b_id", name="ck_research_dup_order"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    research_project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    paper_a_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    paper_b_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False, default="not_duplicate")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


EXTRACTION_STATUSES = (
    "pending",
    "retrieving_sources",
    "extracting",
    "validating",
    "saving",
    "completed",
    "failed",
    "cancelled",
)
ACTIVE_EXTRACTION_STATUSES = EXTRACTION_STATUSES[:5]
EVIDENCE_ORIGINS = ("reported", "ai_inferred")
SECTIONS = (
    "research_problem",
    "objectives",
    "methodology",
    "dataset",
    "evaluation",
    "results",
    "contributions",
    "limitations",
    "future_work",
    "references",
)


class ResearchPaperExtraction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One analysis run of one paper (Phase 7 M7.3). It is also the background job: status moves
    pending -> ... -> completed|failed|cancelled. Every run keeps its own version number and its
    own evidence, so re-analysis never overwrites an earlier result."""

    __tablename__ = "research_paper_extractions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["research_paper_id", "user_id"],
            ["research_papers.id", "research_papers.user_id"],
            ondelete="CASCADE",
            name="fk_research_extractions_paper_owner",
        ),
        UniqueConstraint("id", "user_id", name="uq_research_extractions_id_user"),
        UniqueConstraint("research_paper_id", "version_number", name="uq_research_extractions_ver"),
        CheckConstraint(
            f"status IN ({_sql(EXTRACTION_STATUSES)})", name="ck_research_extractions_status"
        ),
        Index(
            "uq_research_extractions_one_active",
            "research_paper_id",
            unique=True,
            postgresql_where=text(f"status IN ({_sql(ACTIVE_EXTRACTION_STATUSES)})"),
        ),
        Index("ix_research_extractions_user_status", "user_id", "status"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    research_paper_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extraction_version: Mapped[str] = mapped_column(String(32), nullable=False)
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_identifier: Mapped[str | None] = mapped_column(String(128), nullable=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    document_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    structured_result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    result_stats: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    source_stats: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # Fixed error vocabulary only (never provider text or paper text).
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    provider_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    celery_task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ResearchEvidence(UUIDPrimaryKeyMixin, Base):
    """One supporting quotation for one extracted claim (spec 25.5). Claims with several quotations
    have several rows sharing (extraction_id, claim_type, claim_index). `chunk_id` is not a foreign
    key: re-processing a document replaces its chunks, and the quotation stays as the record."""

    __tablename__ = "research_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["extraction_id", "user_id"],
            ["research_paper_extractions.id", "research_paper_extractions.user_id"],
            ondelete="CASCADE",
            name="fk_research_evidence_extraction_owner",
        ),
        ForeignKeyConstraint(
            ["research_paper_id", "research_project_id"],
            ["research_papers.id", "research_papers.research_project_id"],
            ondelete="CASCADE",
            name="fk_research_evidence_paper_project",
        ),
        CheckConstraint(f"claim_type IN ({_sql(SECTIONS)})", name="ck_research_evidence_type"),
        CheckConstraint(
            f"evidence_origin IN ({_sql(EVIDENCE_ORIGINS)})", name="ck_research_evidence_origin"
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_research_evidence_confidence",
        ),
        Index("ix_research_evidence_extraction", "extraction_id", "claim_type", "claim_index"),
        Index("ix_research_evidence_paper", "user_id", "research_paper_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    research_project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    research_paper_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    extraction_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    claim_type: Mapped[str] = mapped_column(String(24), nullable=False)
    claim_index: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    document_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    supporting_text: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence_origin: Mapped[str] = mapped_column(String(16), nullable=False, default="reported")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ResearchPaperNote(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A researcher note on a paper, optionally attached to one analysis section. Analysis runs
    never read or change notes, so re-analysis cannot overwrite them (spec 25.6)."""

    __tablename__ = "research_paper_notes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["research_paper_id", "user_id"],
            ["research_papers.id", "research_papers.user_id"],
            ondelete="CASCADE",
            name="fk_research_notes_paper_owner",
        ),
        CheckConstraint(
            f"section IS NULL OR section IN ({_sql(SECTIONS)})", name="ck_research_notes_section"
        ),
        Index("ix_research_notes_paper", "user_id", "research_paper_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    research_paper_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    section: Mapped[str | None] = mapped_column(String(24), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)


class ResearchComparison(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A saved comparison of two or more papers of one project (Phase 7 M7.4). `comparison_result`
    is a snapshot built from each paper's analysis at creation time, so it stays readable (and
    honest about which analysis versions it used) when a paper is analysed again. `notes` are the
    researcher's own words per dimension and never change extracted claims."""

    __tablename__ = "research_comparisons"
    __table_args__ = (
        ForeignKeyConstraint(
            ["research_project_id", "user_id"],
            ["research_projects.id", "research_projects.user_id"],
            ondelete="CASCADE",
            name="fk_research_comparisons_project_owner",
        ),
        UniqueConstraint("id", "user_id", name="uq_research_comparisons_id_user"),
        Index("ix_research_comparisons_project", "user_id", "research_project_id", "created_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    research_project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    comparison_configuration: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    comparison_result: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    notes: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class ResearchComparisonPaper(UUIDPrimaryKeyMixin, Base):
    """Which papers a comparison covers, in display order. Removing a paper removes it here; the
    saved snapshot keeps what was compared."""

    __tablename__ = "research_comparison_papers"
    __table_args__ = (
        ForeignKeyConstraint(
            ["comparison_id", "user_id"],
            ["research_comparisons.id", "research_comparisons.user_id"],
            ondelete="CASCADE",
            name="fk_research_comparison_papers_cmp_owner",
        ),
        ForeignKeyConstraint(
            ["research_paper_id", "user_id"],
            ["research_papers.id", "research_papers.user_id"],
            ondelete="CASCADE",
            name="fk_research_comparison_papers_paper_owner",
        ),
        UniqueConstraint("comparison_id", "research_paper_id", name="uq_research_cmp_paper"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    comparison_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    research_paper_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    extraction_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)


MATRIX_ORIGINS = ("extracted", "ai_generated", "researcher")


class ResearchEvidenceMatrix(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A literature-review matrix of one project (Phase 7 M7.5)."""

    __tablename__ = "research_evidence_matrices"
    __table_args__ = (
        ForeignKeyConstraint(
            ["research_project_id", "user_id"],
            ["research_projects.id", "research_projects.user_id"],
            ondelete="CASCADE",
            name="fk_research_matrices_project_owner",
        ),
        UniqueConstraint("id", "user_id", name="uq_research_matrices_id_user"),
        Index("ix_research_matrices_project", "user_id", "research_project_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    research_project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class ResearchEvidenceMatrixColumn(UUIDPrimaryKeyMixin, Base):
    """A matrix column. `source` says where extracted values come from ("meta:title",
    "dimension:methodology", ...); custom columns have no source and are researcher-filled."""

    __tablename__ = "research_evidence_matrix_columns"
    __table_args__ = (
        ForeignKeyConstraint(
            ["matrix_id", "user_id"],
            ["research_evidence_matrices.id", "research_evidence_matrices.user_id"],
            ondelete="CASCADE",
            name="fk_research_matrix_columns_matrix_owner",
        ),
        UniqueConstraint("id", "matrix_id", name="uq_research_matrix_columns_id_matrix"),
        UniqueConstraint("matrix_id", "column_key", name="uq_research_matrix_columns_key"),
        Index("ix_research_matrix_columns_matrix", "matrix_id", "position"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    matrix_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    column_key: Mapped[str] = mapped_column(String(60), nullable=False)
    title: Mapped[str] = mapped_column(String(80), nullable=False)
    data_type: Mapped[str] = mapped_column(String(12), nullable=False, default="text")
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str | None] = mapped_column(String(60), nullable=True)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class ResearchEvidenceMatrixEntry(UUIDPrimaryKeyMixin, Base):
    """One cell. `value_origin` keeps extracted paper information, AI interpretation and the
    researcher's own words apart; a refresh never overwrites a researcher value. `evidence_ids`
    point at `research_evidence` rows (no foreign key: a re-analysis keeps its own evidence)."""

    __tablename__ = "research_evidence_matrix_entries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["matrix_id", "user_id"],
            ["research_evidence_matrices.id", "research_evidence_matrices.user_id"],
            ondelete="CASCADE",
            name="fk_research_matrix_entries_matrix_owner",
        ),
        ForeignKeyConstraint(
            ["research_paper_id", "user_id"],
            ["research_papers.id", "research_papers.user_id"],
            ondelete="CASCADE",
            name="fk_research_matrix_entries_paper_owner",
        ),
        ForeignKeyConstraint(
            ["column_id", "matrix_id"],
            ["research_evidence_matrix_columns.id", "research_evidence_matrix_columns.matrix_id"],
            ondelete="CASCADE",
            name="fk_research_matrix_entries_column",
        ),
        UniqueConstraint("matrix_id", "research_paper_id", "column_id", name="uq_research_cell"),
        CheckConstraint(
            f"value_origin IN ({_sql(MATRIX_ORIGINS)})", name="ck_research_matrix_entries_origin"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    matrix_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    research_paper_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    column_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    value_origin: Mapped[str] = mapped_column(String(14), nullable=False, default="extracted")
    evidence_ids: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


GAP_CATEGORIES = (
    "methodological",
    "dataset",
    "population",
    "evaluation",
    "domain",
    "application",
    "generalisation",
    "reproducibility",
    "contradictory_findings",
)
GAP_CONFIDENCE = (
    "strong_candidate",
    "moderate_candidate",
    "preliminary_candidate",
    "insufficient_evidence",
)
GAP_STATUSES = ("suggested", "accepted", "rejected", "investigating")
GAP_ROLES = ("supporting", "counter_evidence", "contextual")


class ResearchGap(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A candidate research gap (Phase 7 M7.6). It only describes the analysed collection of one
    project; it never claims that no other research exists."""

    __tablename__ = "research_gaps"
    __table_args__ = (
        ForeignKeyConstraint(
            ["research_project_id", "user_id"],
            ["research_projects.id", "research_projects.user_id"],
            ondelete="CASCADE",
            name="fk_research_gaps_project_owner",
        ),
        UniqueConstraint("id", "user_id", name="uq_research_gaps_id_user"),
        CheckConstraint(f"category IN ({_sql(GAP_CATEGORIES)})", name="ck_research_gaps_category"),
        CheckConstraint(
            f"confidence_label IN ({_sql(GAP_CONFIDENCE)})", name="ck_research_gaps_confidence"
        ),
        CheckConstraint(
            f"validation_status IN ({_sql(GAP_STATUSES)})", name="ck_research_gaps_status"
        ),
        Index("ix_research_gaps_project", "user_id", "research_project_id", "validation_status"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    research_project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    confidence_label: Mapped[str] = mapped_column(String(24), nullable=False)
    limitations: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_direction: Mapped[str] = mapped_column(Text, nullable=False)
    validation_status: Mapped[str] = mapped_column(String(14), nullable=False, default="suggested")
    analysis_version: Mapped[str] = mapped_column(String(16), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    edited_by_user: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    researcher_notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class ResearchGapEvidence(UUIDPrimaryKeyMixin, Base):
    """The claim behind a gap, with its role. `claim_text` is a copy so the gap stays readable if
    the analysis is run again."""

    __tablename__ = "research_gap_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["gap_id", "user_id"],
            ["research_gaps.id", "research_gaps.user_id"],
            ondelete="CASCADE",
            name="fk_research_gap_evidence_gap_owner",
        ),
        ForeignKeyConstraint(
            ["research_paper_id", "user_id"],
            ["research_papers.id", "research_papers.user_id"],
            ondelete="CASCADE",
            name="fk_research_gap_evidence_paper_owner",
        ),
        CheckConstraint(
            f"evidence_role IN ({_sql(GAP_ROLES)})", name="ck_research_gap_evidence_role"
        ),
        Index("ix_research_gap_evidence_gap", "gap_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    gap_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    research_paper_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    research_evidence_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("research_evidence.id", ondelete="SET NULL"), nullable=True
    )
    evidence_role: Mapped[str] = mapped_column(String(16), nullable=False)
    claim_type: Mapped[str] = mapped_column(String(24), nullable=False)
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)


CONTRADICTION_CATEGORIES = (
    "genuine",
    "context_dependent",
    "metric_incompatible",
    "insufficient_evidence",
)
CONTRADICTION_CONFIDENCE = ("moderate", "low")
CONTRADICTION_REVIEW = ("unreviewed", "genuine", "context_dependent", "dismissed")


class ResearchContradiction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A pair of claims from two papers of one project that appear to conflict (Phase 7 M7.7). The
    claim text, quotation and page are copied so the record stays readable after a re-analysis; the
    evidence ids are optional links that become NULL if the evidence row is replaced."""

    __tablename__ = "research_contradictions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["research_project_id", "user_id"],
            ["research_projects.id", "research_projects.user_id"],
            ondelete="CASCADE",
            name="fk_research_contradictions_project_owner",
        ),
        ForeignKeyConstraint(
            ["paper_a_id", "user_id"],
            ["research_papers.id", "research_papers.user_id"],
            ondelete="CASCADE",
            name="fk_research_contradictions_paper_a_owner",
        ),
        ForeignKeyConstraint(
            ["paper_b_id", "user_id"],
            ["research_papers.id", "research_papers.user_id"],
            ondelete="CASCADE",
            name="fk_research_contradictions_paper_b_owner",
        ),
        UniqueConstraint("id", "user_id", name="uq_research_contradictions_id_user"),
        CheckConstraint(
            f"category IN ({_sql(CONTRADICTION_CATEGORIES)})", name="ck_research_contradictions_cat"
        ),
        CheckConstraint(
            f"confidence_label IN ({_sql(CONTRADICTION_CONFIDENCE)})",
            name="ck_research_contradictions_conf",
        ),
        CheckConstraint(
            f"review_status IN ({_sql(CONTRADICTION_REVIEW)})",
            name="ck_research_contradictions_review",
        ),
        Index(
            "ix_research_contradictions_project", "user_id", "research_project_id", "review_status"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    research_project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    paper_a_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    paper_b_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    claim_a_text: Mapped[str] = mapped_column(Text, nullable=False)
    claim_b_text: Mapped[str] = mapped_column(Text, nullable=False)
    claim_a_type: Mapped[str] = mapped_column(String(24), nullable=False)
    claim_b_type: Mapped[str] = mapped_column(String(24), nullable=False)
    evidence_a_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("research_evidence.id", ondelete="SET NULL"), nullable=True
    )
    evidence_b_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("research_evidence.id", ondelete="SET NULL"), nullable=True
    )
    quote_a: Mapped[str | None] = mapped_column(Text, nullable=True)
    quote_b: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_a: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_b: Mapped[int | None] = mapped_column(Integer, nullable=True)
    conditions: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    category: Mapped[str] = mapped_column(String(24), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    confidence_label: Mapped[str] = mapped_column(String(10), nullable=False)
    review_status: Mapped[str] = mapped_column(String(24), nullable=False, default="unreviewed")
    researcher_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis_version: Mapped[str] = mapped_column(String(16), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)


CITATION_STYLES = ("apa", "ieee", "mla", "chicago", "harvard")


class ResearchCitation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A formatted reference for one paper in one style (Phase 7 M7.8). The metadata used is kept as
    a snapshot so the citation can be regenerated accurately and so a later change to the paper's
    metadata can be detected."""

    __tablename__ = "research_citations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["research_project_id", "user_id"],
            ["research_projects.id", "research_projects.user_id"],
            ondelete="CASCADE",
            name="fk_research_citations_project_owner",
        ),
        ForeignKeyConstraint(
            ["research_paper_id", "user_id"],
            ["research_papers.id", "research_papers.user_id"],
            ondelete="CASCADE",
            name="fk_research_citations_paper_owner",
        ),
        UniqueConstraint("id", "user_id", name="uq_research_citations_id_user"),
        UniqueConstraint(
            "user_id",
            "research_project_id",
            "research_paper_id",
            "citation_style",
            name="uq_research_citations_paper_style",
        ),
        CheckConstraint(
            f"citation_style IN ({_sql(CITATION_STYLES)})", name="ck_research_citations_style"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    research_project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    research_paper_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    citation_style: Mapped[str] = mapped_column(String(12), nullable=False)
    formatted_citation: Mapped[str] = mapped_column(Text, nullable=False)
    in_text_citation: Mapped[str] = mapped_column(String(400), nullable=False)
    metadata_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


DRAFT_TYPES = ("research_paper", "literature_review", "proposal", "report", "notes")
DRAFT_STATUSES = ("draft", "in_review", "final")
DRAFT_SOURCES = ("created", "manual", "ai_suggestion", "restore")


class ResearchDraft(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A researcher's draft (Phase 7 M7.9). `content` is Markdown; a citation is the marker
    `{{cite:<paper id>}}`, resolved against the project's papers when the draft is previewed or
    exported. `version_number` is the number of the latest saved version (optimistic locking)."""

    __tablename__ = "research_drafts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["research_project_id", "user_id"],
            ["research_projects.id", "research_projects.user_id"],
            ondelete="CASCADE",
            name="fk_research_drafts_project_owner",
        ),
        UniqueConstraint("id", "user_id", name="uq_research_drafts_id_user"),
        CheckConstraint(f"document_type IN ({_sql(DRAFT_TYPES)})", name="ck_research_drafts_type"),
        CheckConstraint(f"status IN ({_sql(DRAFT_STATUSES)})", name="ck_research_drafts_status"),
        CheckConstraint(
            f"citation_style IN ({_sql(CITATION_STYLES)})", name="ck_research_drafts_style"
        ),
        Index("ix_research_drafts_project", "user_id", "research_project_id", "updated_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    research_project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    document_type: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="draft")
    citation_style: Mapped[str] = mapped_column(String(12), nullable=False, default="apa")
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class ResearchDraftVersion(UUIDPrimaryKeyMixin, Base):
    """One saved state of a draft. Never edited; a restore adds a new version."""

    __tablename__ = "research_draft_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["draft_id", "user_id"],
            ["research_drafts.id", "research_drafts.user_id"],
            ondelete="CASCADE",
            name="fk_research_draft_versions_draft_owner",
        ),
        UniqueConstraint("draft_id", "version_number", name="uq_research_draft_versions_number"),
        CheckConstraint(
            f"change_source IN ({_sql(DRAFT_SOURCES)})", name="ck_research_draft_versions_source"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    draft_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title_snapshot: Mapped[str] = mapped_column(String(200), nullable=False)
    content_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    change_summary: Mapped[str] = mapped_column(String(300), nullable=False)
    change_source: Mapped[str] = mapped_column(String(14), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


CONCEPT_LINK_STATUSES = ("suggested", "confirmed", "rejected")
CONCEPT_MATCH_KINDS = ("name", "alias")


class ResearchConceptLink(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A suggested or confirmed link between an analysed paper and an existing knowledge node of the
    same workspace (Phase 7 M7.10). It records why the paper relates to the concept (the verified
    claim that names it) and never touches the graph itself or the mastery of the learner."""

    __tablename__ = "research_concept_links"
    __table_args__ = (
        ForeignKeyConstraint(
            ["research_project_id", "user_id"],
            ["research_projects.id", "research_projects.user_id"],
            ondelete="CASCADE",
            name="fk_research_concept_links_project_owner",
        ),
        ForeignKeyConstraint(
            ["research_paper_id", "user_id"],
            ["research_papers.id", "research_papers.user_id"],
            ondelete="CASCADE",
            name="fk_research_concept_links_paper_owner",
        ),
        ForeignKeyConstraint(
            ["knowledge_node_id", "user_id"],
            ["knowledge_nodes.id", "knowledge_nodes.user_id"],
            ondelete="CASCADE",
            name="fk_research_concept_links_node_owner",
        ),
        UniqueConstraint(
            "user_id", "research_paper_id", "knowledge_node_id", name="uq_research_concept_links"
        ),
        CheckConstraint(
            f"link_status IN ({_sql(CONCEPT_LINK_STATUSES)})",
            name="ck_research_concept_links_status",
        ),
        CheckConstraint(
            f"match_kind IN ({_sql(CONCEPT_MATCH_KINDS)})", name="ck_research_concept_links_match"
        ),
        Index("ix_research_concept_links_node", "user_id", "knowledge_node_id", "link_status"),
        Index("ix_research_concept_links_project", "user_id", "research_project_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    research_project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    research_paper_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    knowledge_node_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    match_kind: Mapped[str] = mapped_column(String(8), nullable=False)
    matched_text: Mapped[str] = mapped_column(String(200), nullable=False)
    link_status: Mapped[str] = mapped_column(String(12), nullable=False, default="suggested")
    # Provenance (spec 32.4): the analysis run, the evidence row, the source document and page.
    extraction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_paper_extractions.id", ondelete="SET NULL"),
        nullable=True,
    )
    research_evidence_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("research_evidence.id", ondelete="SET NULL"), nullable=True
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    claim_type: Mapped[str] = mapped_column(String(24), nullable=False)
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    mention_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
