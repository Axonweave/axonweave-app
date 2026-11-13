"""Persistence for contradictions (Phase 7 M7.7). Every query is scoped by `user_id` (rule 3)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research import ResearchContradiction

C = ResearchContradiction


class ResearchContradictionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get(self, user_id: uuid.UUID, contradiction_id: uuid.UUID) -> C | None:
        return (
            await self._db.execute(select(C).where(C.user_id == user_id, C.id == contradiction_id))
        ).scalar_one_or_none()

    async def list_for_project(
        self,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        *,
        category: str | None,
        review_status: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[C], int]:
        where = [C.user_id == user_id, C.research_project_id == project_id]
        if category:
            where.append(C.category == category)
        if review_status:
            where.append(C.review_status == review_status)
        total = (await self._db.execute(select(func.count(C.id)).where(*where))).scalar_one()
        rows = (
            await self._db.execute(
                select(C)
                .where(*where)
                .order_by(C.created_at.desc(), C.id)
                .limit(limit)
                .offset(offset)
            )
        ).scalars()
        return list(rows), total

    async def all_for_project(self, user_id: uuid.UUID, project_id: uuid.UUID) -> list[C]:
        rows = await self._db.execute(
            select(C).where(C.user_id == user_id, C.research_project_id == project_id)
        )
        return list(rows.scalars())

    async def add(self, row: C) -> C:
        self._db.add(row)
        await self._db.flush()
        return row

    async def delete(self, user_id: uuid.UUID, contradiction_id: uuid.UUID) -> None:
        await self._db.execute(delete(C).where(C.user_id == user_id, C.id == contradiction_id))

    async def delete_many(self, user_id: uuid.UUID, ids: Sequence[uuid.UUID]) -> None:
        if ids:
            await self._db.execute(delete(C).where(C.user_id == user_id, C.id.in_(ids)))
