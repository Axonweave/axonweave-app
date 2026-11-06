import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.database.fk import SetNullColumnsFK

# Spec names (PHASE3_SPEC 6.2). "validating" is a worker-side re-check; a rejected upload never
# creates a row (it is refused with 422 before anything is stored).
PROCESSING_STATUSES = (
    "uploaded",
    "queued",
    "validating",
    "extracting",
    "ocr_processing",
    "normalising",
    "chunking",
    "embedding",
    "indexing",
    "completed",
    "failed",
    "cancelled",
)
_STATUS_SQL = ", ".join(f"'{s}'" for s in PROCESSING_STATUSES)
FILE_TYPES = ("pdf", "pptx", "docx", "txt", "md", "png", "jpg")
_FILE_TYPE_SQL = ", ".join(f"'{s}'" for s in FILE_TYPES)


class Document(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One uploaded document. The placement chain (workspace -> subject -> folder/chapter) is held
    consistent by composite foreign keys (D-09 style). Hard-deleted (D-10, D-66); storage objects
    are removed through the `storage_cleanup` outbox. `processing_status` is a denormalised copy of
    the latest version's status (D-68)."""

    __tablename__ = "documents"
    __table_args__ = (
        # Target for composite ownership FKs from versions, chunks, jobs and citations.
        UniqueConstraint("id", "user_id", name="uq_documents_id_user"),
        ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["workspaces.id", "workspaces.user_id"],
            ondelete="CASCADE",
            name="fk_documents_workspace_owner",
        ),
        ForeignKeyConstraint(
            ["subject_id", "workspace_id"],
            ["subjects.id", "subjects.workspace_id"],
            ondelete="CASCADE",
            name="fk_documents_subject_workspace",
        ),
        # A folder/chapter going away must not delete the document: only its link is cleared.
        SetNullColumnsFK(
            ["folder_id", "subject_id"],
            ["folders.id", "folders.subject_id"],
            set_null=["folder_id"],
            name="fk_documents_folder_subject",
        ),
        SetNullColumnsFK(
            ["chapter_id", "subject_id"],
            ["chapters.id", "chapters.subject_id"],
            set_null=["chapter_id"],
            name="fk_documents_chapter_subject",
        ),
        # Composite FKs are not checked when one column is NULL, so require the parent explicitly.
        CheckConstraint(
            "folder_id IS NULL OR subject_id IS NOT NULL", name="ck_documents_folder_needs_subject"
        ),
        CheckConstraint(
            "chapter_id IS NULL OR subject_id IS NOT NULL",
            name="ck_documents_chapter_needs_subject",
        ),
        CheckConstraint(f"processing_status IN ({_STATUS_SQL})", name="ck_documents_status"),
        CheckConstraint(f"file_type IN ({_FILE_TYPE_SQL})", name="ck_documents_file_type"),
        CheckConstraint("file_size >= 0", name="ck_documents_file_size"),
        CheckConstraint("latest_version >= 1", name="ck_documents_latest_version"),
        CheckConstraint(
            "active_version IS NULL OR (active_version >= 1 AND active_version <= latest_version)",
            name="ck_documents_active_version",
        ),
        Index("ix_documents_user_created", "user_id", "created_at"),
        Index("ix_documents_user_workspace_subject", "user_id", "workspace_id", "subject_id"),
        Index("ix_documents_user_status", "user_id", "processing_status"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    subject_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    folder_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    chapter_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(16), nullable=False)
    mime_type: Mapped[str] = mapped_column(
        String(100), nullable=False
    )  # detected, not the browser's
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA-256 hex
    processing_status: Mapped[str] = mapped_column(String(24), nullable=False, default="uploaded")
    active_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latest_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DocumentVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One uploaded file version. `processing_status` here is authoritative (D-68)."""

    __tablename__ = "document_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["document_id", "user_id"],
            ["documents.id", "documents.user_id"],
            ondelete="CASCADE",
            name="fk_document_versions_document_owner",
        ),
        UniqueConstraint("document_id", "version_number", name="uq_document_versions_number"),
        # Targets for chunk and job FKs: a child can only reference a version of its own document.
        UniqueConstraint("id", "document_id", name="uq_document_versions_id_document"),
        UniqueConstraint("storage_key", name="uq_document_versions_storage_key"),
        CheckConstraint("version_number >= 1", name="ck_document_versions_number"),
        CheckConstraint(
            f"processing_status IN ({_STATUS_SQL})", name="ck_document_versions_status"
        ),
        CheckConstraint("file_size >= 0", name="ck_document_versions_file_size"),
        CheckConstraint(
            "(page_count IS NULL OR page_count >= 0) AND (slide_count IS NULL OR slide_count >= 0) "
            "AND (word_count IS NULL OR word_count >= 0)",
            name="ck_document_versions_counts",
        ),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)  # generated, never exposed
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    processing_status: Mapped[str] = mapped_column(String(24), nullable=False, default="uploaded")
    extraction_method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ocr_used: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    ocr_mean_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    slide_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    word_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    warnings: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )  # safe warning codes only
    pipeline_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    index_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
