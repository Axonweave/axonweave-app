import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, UUIDPrimaryKeyMixin
from app.database.fk import SetNullColumnsFK


class MessageCitation(UUIDPrimaryKeyMixin, Base):
    """A source shown with an assistant answer, written from retrieved chunks only (D-75).

    Page, slide, name and heading come from the database, never from model text. When the document
    or chunk is deleted the links are cleared and `available` is set false by the service, which
    also clears `snippet` and `section_heading` (D-66); only the document name and page remain.
    """

    __tablename__ = "message_citations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["message_id", "user_id"],
            ["messages.id", "messages.user_id"],
            ondelete="CASCADE",
            name="fk_message_citations_message_owner",
        ),
        # Owner is part of the link, so a citation can never point at another user's chunk or
        # document; deleting the target clears only the link column (keeps user_id).
        SetNullColumnsFK(
            ["chunk_id", "user_id"],
            ["document_chunks.id", "document_chunks.user_id"],
            set_null=["chunk_id"],
            name="fk_message_citations_chunk_owner",
        ),
        SetNullColumnsFK(
            ["document_id", "user_id"],
            ["documents.id", "documents.user_id"],
            set_null=["document_id"],
            name="fk_message_citations_document_owner",
        ),
        UniqueConstraint("message_id", "rank", name="uq_message_citations_message_rank"),
        CheckConstraint("rank >= 1", name="ck_message_citations_rank"),
        CheckConstraint(
            "page_number IS NULL OR page_number >= 1", name="ck_message_citations_page"
        ),
        CheckConstraint(
            "slide_number IS NULL OR slide_number >= 1", name="ck_message_citations_slide"
        ),
        Index("ix_message_citations_user", "user_id"),
        Index("ix_message_citations_document", "document_id"),
    )

    message_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)  # the [n] shown in the answer
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    document_name: Mapped[str] = mapped_column(String(255), nullable=False)
    document_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    slide_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section_heading: Mapped[str | None] = mapped_column(Text, nullable=True)
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    available: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
