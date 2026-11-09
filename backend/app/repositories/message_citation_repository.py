"""Citation persistence. Every query is scoped by the owning user (rule 3)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message_citation import MessageCitation
from app.repositories.retrieval_repository import ChunkHit

SNIPPET_CHARS = 300


class MessageCitationRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def add_for_message(
        self,
        *,
        user_id: uuid.UUID,
        message_id: uuid.UUID,
        ranked: Sequence[tuple[int, ChunkHit]],
    ) -> list[MessageCitation]:
        rows = [
            MessageCitation(
                message_id=message_id,
                user_id=user_id,
                rank=rank,
                chunk_id=hit.chunk_id,
                document_id=hit.document_id,
                document_name=hit.document_name[:255],
                page_number=hit.page_number,
                slide_number=hit.slide_number,
                section_heading=hit.section_heading,
                snippet=hit.content[:SNIPPET_CHARS],
                score=hit.score,
                available=True,
            )
            for rank, hit in ranked
        ]
        self._db.add_all(rows)
        await self._db.flush()
        return rows

    async def list_for_message(
        self, *, user_id: uuid.UUID, message_id: uuid.UUID
    ) -> list[MessageCitation]:
        stmt = (
            select(MessageCitation)
            .where(MessageCitation.message_id == message_id, MessageCitation.user_id == user_id)
            .order_by(MessageCitation.rank)
        )
        return list((await self._db.execute(stmt)).scalars())

    async def get_owned(
        self, *, user_id: uuid.UUID, citation_id: uuid.UUID
    ) -> MessageCitation | None:
        stmt = select(MessageCitation).where(
            MessageCitation.id == citation_id, MessageCitation.user_id == user_id
        )
        return (await self._db.execute(stmt)).scalar_one_or_none()

    async def mark_document_unavailable(
        self, *, user_id: uuid.UUID, document_id: uuid.UUID
    ) -> None:
        """Deleted source (D-66): keep only the document name and page."""
        await self._db.execute(
            update(MessageCitation)
            .where(MessageCitation.user_id == user_id, MessageCitation.document_id == document_id)
            .values(available=False, snippet=None, section_heading=None)
        )
