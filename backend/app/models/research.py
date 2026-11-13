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
