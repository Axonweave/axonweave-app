import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    Computed,
    DateTime,
    Float,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, UUIDPrimaryKeyMixin
from app.database.vector import EMBEDDING_COLUMN_DIMENSIONS

# Full-text configuration baked into the generated column (UI is English-only, D-35). Changing it
# needs a migration and a reindex.
FTS_CONFIG = "english"


class DocumentChunk(UUIDPrimaryKeyMixin, Base):
    """A retrievable piece of one document version (D-67).

    `user_id` is part of the document FK, so a chunk can never belong to a document of another
    owner. The workspace/subject/folder/chapter columns are denormalised copies kept by the document
    move service; they are informational and are NEVER used for authorisation: retrieval filters by
    `user_id` and a verified document id set (ScopeResolver). Only chunks of the document's active,
    completed version with the current `index_version` are searchable.
    """

    __tablename__ = "document_chunks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["document_id", "user_id"],
            ["documents.id", "documents.user_id"],
            ondelete="CASCADE",
            name="fk_document_chunks_document_owner",
        ),
        ForeignKeyConstraint(
            ["document_version_id", "document_id"],
            ["document_versions.id", "document_versions.document_id"],
            ondelete="CASCADE",
            name="fk_document_chunks_version_document",
        ),
        UniqueConstraint(
            "document_version_id", "chunk_index", name="uq_document_chunks_version_index"
        ),
        # Target for message_citations ownership FKs.
        UniqueConstraint("id", "user_id", name="uq_document_chunks_id_user"),
        CheckConstraint("chunk_index >= 0", name="ck_document_chunks_index"),
        CheckConstraint("page_number IS NULL OR page_number >= 1", name="ck_document_chunks_page"),
        CheckConstraint(
            "slide_number IS NULL OR slide_number >= 1", name="ck_document_chunks_slide"
        ),
        CheckConstraint(
            "token_count >= 0 AND char_count >= 0", name="ck_document_chunks_sizes_non_negative"
        ),
        # Never mix models or dimensions in one index (D-69): a stored vector must say which model
        # made it and must have exactly the column's dimension.
        CheckConstraint(
            "embedding IS NULL OR (embedding_model IS NOT NULL AND "
            f"embedding_dimensions = {EMBEDDING_COLUMN_DIMENSIONS})",
            name="ck_document_chunks_embedding_meta",
        ),
        CheckConstraint("index_version >= 1", name="ck_document_chunks_index_version"),
        Index("ix_document_chunks_user_document", "user_id", "document_id"),
        Index("ix_document_chunks_user_scope", "user_id", "workspace_id", "subject_id"),
        Index("ix_document_chunks_content_tsv", "content_tsv", postgresql_using="gin"),
        # No ANN (HNSW/IVFFlat) index on `embedding` yet: baseline is exact filtered search and an
        # index is added only after measurement with the real filters (D-73).
    )

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    document_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    subject_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    folder_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    chapter_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_tsv: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed(f"to_tsvector('{FTS_CONFIG}', coalesce(content, ''))", persisted=True),
        nullable=True,
    )
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    slide_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section_heading: Mapped[str | None] = mapped_column(Text, nullable=True)
    bboxes: Mapped[Any | None] = mapped_column(JSONB, nullable=True)  # PDF block rectangles
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extraction_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    embedding: Mapped[Any | None] = mapped_column(
        Vector(EMBEDDING_COLUMN_DIMENSIONS), nullable=True
    )
    embedding_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    embedding_dimensions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    index_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
