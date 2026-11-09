"""Citation and source-passage lookups. Ownership is checked on every call (spec 19.5, rule 2)."""

from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentVersion
from app.models.document_chunk import DocumentChunk
from app.models.message_citation import MessageCitation
from app.repositories.ai_message_repository import AiMessageRepository
from app.repositories.message_citation_repository import MessageCitationRepository


def _not_found(code: str, message: str) -> HTTPException:
    return HTTPException(404, detail={"code": code, "message": message})


def redact_if_unavailable(citation: MessageCitation) -> MessageCitation:
    """A deleted source keeps only its name and page (D-66). Cascade deletes (subject, workspace,
    account) null the link without touching the row, so this is enforced when reading too."""
    if citation.document_id is None or not citation.available:
        citation.available = False
        citation.snippet = None
        citation.section_heading = None
    return citation


class CitationService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._citations = MessageCitationRepository(db)

    async def get(self, *, user_id: uuid.UUID, citation_id: uuid.UUID) -> MessageCitation:
        row = await self._citations.get_owned(user_id=user_id, citation_id=citation_id)
        if row is None:
            raise _not_found("CITATION_NOT_FOUND", "Citation not found.")
        return redact_if_unavailable(row)

    async def for_message(
        self, *, user_id: uuid.UUID, message_id: uuid.UUID
    ) -> list[MessageCitation]:
        message = await AiMessageRepository(self._db).get_owned(
            message_id=message_id, user_id=user_id
        )
        if message is None:
            raise _not_found("MESSAGE_NOT_FOUND", "Message not found.")
        rows = await self._citations.list_for_message(user_id=user_id, message_id=message_id)
        return [redact_if_unavailable(r) for r in rows]

    async def source_passage(
        self, *, user_id: uuid.UUID, document_id: uuid.UUID, chunk_id: uuid.UUID
    ) -> tuple[DocumentChunk, str]:
        """The chunk text of an owned document's active version, for the source panel."""
        stmt = (
            select(DocumentChunk, Document.display_name)
            .join(Document, Document.id == DocumentChunk.document_id)
            .join(
                DocumentVersion,
                (DocumentVersion.id == DocumentChunk.document_version_id)
                & (DocumentVersion.version_number == Document.active_version),
            )
            .where(
                DocumentChunk.id == chunk_id,
                DocumentChunk.document_id == document_id,
                DocumentChunk.user_id == user_id,
                Document.user_id == user_id,
            )
        )
        row = (await self._db.execute(stmt)).first()
        if row is None:
            raise _not_found("SOURCE_NOT_FOUND", "Source not found.")
        return row[0], row[1]
