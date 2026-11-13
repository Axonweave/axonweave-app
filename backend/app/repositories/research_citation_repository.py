"""Persistence for citations (Phase 7 M7.8). Every query is scoped by `user_id` (rule 3)."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research import ResearchCitation

C = ResearchCitation


class ResearchCitationRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get(self, user_id: uuid.UUID, citation_id: uuid.UUID) -> C | None:
        return (
            await self._db.execute(select(C).where(C.user_id == user_id, C.id == citation_id))
        ).scalar_one_or_none()

    async def get_many(
        self, user_id: uuid.UUID, project_id: uuid.UUID, ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, C]:
        rows = await self._db.execute(
            select(C).where(
                C.user_id == user_id, C.research_project_id == project_id, C.id.in_(ids)
            )
        )
        return {c.id: c for c in rows.scalars()}

    async def list_for_project(
        self, user_id: uuid.UUID, project_id: uuid.UUID, style: str | None
    ) -> list[C]:
        stmt = select(C).where(C.user_id == user_id, C.research_project_id == project_id)
        if style:
            stmt = stmt.where(C.citation_style == style)
        rows = await self._db.execute(stmt.order_by(C.created_at, C.id))
        return list(rows.scalars())

    async def get_for_paper(
        self, user_id: uuid.UUID, project_id: uuid.UUID, paper_id: uuid.UUID, style: str
    ) -> C | None:
        return (
            await self._db.execute(
                select(C).where(
                    C.user_id == user_id,
                    C.research_project_id == project_id,
                    C.research_paper_id == paper_id,
                    C.citation_style == style,
                )
            )
        ).scalar_one_or_none()

    async def add(self, row: C) -> C:
        self._db.add(row)
        await self._db.flush()
        return row

    async def delete(self, user_id: uuid.UUID, citation_id: uuid.UUID) -> None:
        await self._db.execute(delete(C).where(C.user_id == user_id, C.id == citation_id))
