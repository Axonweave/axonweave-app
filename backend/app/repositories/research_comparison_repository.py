"""Persistence for saved paper comparisons (Phase 7 M7.4). Every query is filtered by `user_id`
(rule 3): a comparison that belongs to someone else behaves exactly like a missing one."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research import ResearchComparison, ResearchComparisonPaper


class ResearchComparisonRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get(self, user_id: uuid.UUID, comparison_id: uuid.UUID) -> ResearchComparison | None:
        return (
            await self._db.execute(
                select(ResearchComparison).where(
                    ResearchComparison.user_id == user_id, ResearchComparison.id == comparison_id
                )
            )
        ).scalar_one_or_none()

    async def list_for_project(
        self, user_id: uuid.UUID, project_id: uuid.UUID, *, limit: int, offset: int
    ) -> tuple[list[ResearchComparison], int]:
        where = (
            ResearchComparison.user_id == user_id,
            ResearchComparison.research_project_id == project_id,
        )
        total = (
            await self._db.execute(select(func.count(ResearchComparison.id)).where(*where))
        ).scalar_one()
        rows = (
            await self._db.execute(
                select(ResearchComparison)
                .where(*where)
                .order_by(ResearchComparison.created_at.desc(), ResearchComparison.id)
                .limit(limit)
                .offset(offset)
            )
        ).scalars()
        return list(rows), total

    async def add(
        self, comparison: ResearchComparison, papers: Sequence[ResearchComparisonPaper]
    ) -> ResearchComparison:
        self._db.add(comparison)
        await self._db.flush()
        for link in papers:
            link.comparison_id = comparison.id
        self._db.add_all(papers)
        await self._db.flush()
        return comparison

    async def paper_ids(self, user_id: uuid.UUID, comparison_id: uuid.UUID) -> list[uuid.UUID]:
        rows = await self._db.execute(
            select(ResearchComparisonPaper.research_paper_id)
            .where(
                ResearchComparisonPaper.user_id == user_id,
                ResearchComparisonPaper.comparison_id == comparison_id,
            )
            .order_by(ResearchComparisonPaper.position)
        )
        return list(rows.scalars())

    async def delete(self, user_id: uuid.UUID, comparison_id: uuid.UUID) -> None:
        await self._db.execute(
            delete(ResearchComparison).where(
                ResearchComparison.user_id == user_id, ResearchComparison.id == comparison_id
            )
        )
