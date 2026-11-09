import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import case, delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_chunk import DocumentChunk

_BATCH = 200


class DocumentChunkRepository:
    """SQL for chunks. Reads are always scoped by user_id AND document_id."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def replace_for_version(
        self,
        *,
        user_id: uuid.UUID,
        document_id: uuid.UUID,
        version_id: uuid.UUID,
        scope: dict[str, uuid.UUID | None],
        rows: Sequence[dict[str, Any]],
        index_version: int,
    ) -> int:
        """Delete this version's chunks and insert the new ones. The caller's transaction makes the
        swap atomic, so a retry or a duplicate run can never leave duplicate or half-written chunks
        (D-68)."""
        await self._db.execute(
            delete(DocumentChunk).where(
                DocumentChunk.document_version_id == version_id,
                DocumentChunk.user_id == user_id,
            )
        )
        base = {
            "user_id": user_id,
            "document_id": document_id,
            "document_version_id": version_id,
            "index_version": index_version,
            **scope,
        }
        for start in range(0, len(rows), _BATCH):
            batch = [{**base, **row} for row in rows[start : start + _BATCH]]
            await self._db.execute(insert(DocumentChunk), batch)
        return len(rows)

    async def count_for_version(self, *, user_id: uuid.UUID, version_id: uuid.UUID) -> int:
        value = await self._db.execute(
            select(func.count(DocumentChunk.id)).where(
                DocumentChunk.document_version_id == version_id, DocumentChunk.user_id == user_id
            )
        )
        return int(value.scalar_one())

    async def pages(
        self, *, user_id: uuid.UUID, document_id: uuid.UUID, version_id: uuid.UUID
    ) -> list[dict[str, Any]]:
        """One row per page or slide: how many chunks and characters it produced."""
        unit = func.coalesce(DocumentChunk.page_number, DocumentChunk.slide_number)
        kind = func.min(case((DocumentChunk.slide_number.is_not(None), "slide"), else_="page"))
        rows = await self._db.execute(
            select(
                unit.label("number"),
                kind.label("kind"),
                func.count(DocumentChunk.id).label("chunks"),
                func.sum(DocumentChunk.char_count).label("chars"),
            )
            .where(
                DocumentChunk.document_id == document_id,
                DocumentChunk.user_id == user_id,
                DocumentChunk.document_version_id == version_id,
                unit.is_not(None),
            )
            .group_by(unit)
            .order_by(unit)
        )
        return [
            {"number": r.number, "kind": r.kind, "chunk_count": r.chunks, "char_count": r.chars}
            for r in rows
        ]

    async def content(
        self,
        *,
        user_id: uuid.UUID,
        document_id: uuid.UUID,
        version_id: uuid.UUID,
        page: int | None,
        slide: int | None,
        limit: int,
        offset: int,
    ) -> tuple[list[DocumentChunk], int]:
        conditions = [
            DocumentChunk.document_id == document_id,
            DocumentChunk.user_id == user_id,
            DocumentChunk.document_version_id == version_id,
        ]
        if page is not None:
            conditions.append(DocumentChunk.page_number == page)
        if slide is not None:
            conditions.append(DocumentChunk.slide_number == slide)
        total = (
            await self._db.execute(select(func.count(DocumentChunk.id)).where(*conditions))
        ).scalar_one()
        rows = (
            await self._db.execute(
                select(DocumentChunk)
                .where(*conditions)
                .order_by(DocumentChunk.chunk_index)
                .limit(limit)
                .offset(offset)
            )
        ).scalars()
        return list(rows), int(total)
