"""Owner-scoped reads of document chunks for generation (D-79).

Every query filters by `user_id` AND by a document id set that ScopeResolver verified, and reads
only chunks of the document's active version at the current index version, the same rule retrieval
uses. Nothing fetches by chunk id alone."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentVersion
from app.models.document_chunk import DocumentChunk


@dataclass(frozen=True)
class ChunkRow:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    chunk_index: int
    content: str
    page_number: int | None
    slide_number: int | None
    section_heading: str | None
    token_count: int


@dataclass(frozen=True)
class Placement:
    document_id: uuid.UUID
    workspace_id: uuid.UUID
    subject_id: uuid.UUID | None
    chapter_id: uuid.UUID | None


class StudySourceRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    @staticmethod
    def _active(user_id: uuid.UUID, doc_ids: Sequence[uuid.UUID], index_version: int) -> Any:
        return (
            select(DocumentChunk.id)
            .join(Document, Document.id == DocumentChunk.document_id)
            .join(
                DocumentVersion,
                (DocumentVersion.id == DocumentChunk.document_version_id)
                & (DocumentVersion.version_number == Document.active_version),
            )
            .where(
                DocumentChunk.user_id == user_id,
                Document.user_id == user_id,
                DocumentChunk.document_id.in_(list(doc_ids)),
                DocumentChunk.index_version == index_version,
            )
        )

    async def chunk_index(
        self, user_id: uuid.UUID, doc_ids: Sequence[uuid.UUID], index_version: int
    ) -> list[tuple[uuid.UUID, int]]:
        """(chunk id, tokens) in reading order: document name, document id, chunk index."""
        if not doc_ids:
            return []
        stmt = (
            self._active(user_id, doc_ids, index_version)
            .add_columns(DocumentChunk.token_count)
            .order_by(Document.display_name, Document.id, DocumentChunk.chunk_index)
        )
        return [(row[0], int(row[1])) for row in (await self._db.execute(stmt)).all()]

    async def chunks_by_ids(
        self,
        user_id: uuid.UUID,
        doc_ids: Sequence[uuid.UUID],
        chunk_ids: Sequence[uuid.UUID],
        index_version: int,
    ) -> list[ChunkRow]:
        """The requested chunks, in the order requested; ids outside the verified scope are
        silently absent (they cannot be returned)."""
        if not doc_ids or not chunk_ids:
            return []
        stmt = (
            self._active(user_id, doc_ids, index_version)
            .add_columns(
                DocumentChunk.document_id,
                Document.display_name,
                DocumentChunk.chunk_index,
                DocumentChunk.content,
                DocumentChunk.page_number,
                DocumentChunk.slide_number,
                DocumentChunk.section_heading,
                DocumentChunk.token_count,
            )
            .where(DocumentChunk.id.in_(list(chunk_ids)))
        )
        found = {row[0]: ChunkRow(*row) for row in (await self._db.execute(stmt)).all()}
        return [found[cid] for cid in chunk_ids if cid in found]

    async def placements(self, user_id: uuid.UUID, doc_ids: Sequence[uuid.UUID]) -> list[Placement]:
        if not doc_ids:
            return []
        rows = await self._db.execute(
            select(
                Document.id, Document.workspace_id, Document.subject_id, Document.chapter_id
            ).where(Document.user_id == user_id, Document.id.in_(list(doc_ids)))
        )
        return [Placement(*row) for row in rows.all()]
