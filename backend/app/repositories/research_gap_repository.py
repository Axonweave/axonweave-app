"""Persistence for research gaps (Phase 7 M7.6). Every query is scoped by `user_id` (rule 3)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research import ResearchGap, ResearchGapEvidence

G = ResearchGap
E = ResearchGapEvidence


class ResearchGapRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get(self, user_id: uuid.UUID, gap_id: uuid.UUID) -> G | None:
        return (
            await self._db.execute(select(G).where(G.user_id == user_id, G.id == gap_id))
        ).scalar_one_or_none()

    async def list_for_project(
        self,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        *,
        category: str | None,
        status: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[G], int]:
        where = [G.user_id == user_id, G.research_project_id == project_id]
        if category:
            where.append(G.category == category)
        if status:
            where.append(G.validation_status == status)
        total = (await self._db.execute(select(func.count(G.id)).where(*where))).scalar_one()
        rows = (
            await self._db.execute(
                select(G)
                .where(*where)
                .order_by(G.created_at.desc(), G.id)
                .limit(limit)
                .offset(offset)
            )
        ).scalars()
        return list(rows), total

    async def all_for_project(self, user_id: uuid.UUID, project_id: uuid.UUID) -> list[G]:
        rows = await self._db.execute(
            select(G).where(G.user_id == user_id, G.research_project_id == project_id)
        )
        return list(rows.scalars())

    async def add(self, gap: G) -> G:
        self._db.add(gap)
        await self._db.flush()
        return gap

    async def add_evidence(self, rows: Sequence[E]) -> None:
        self._db.add_all(rows)
        await self._db.flush()

    async def delete(self, user_id: uuid.UUID, gap_id: uuid.UUID) -> None:
        await self._db.execute(delete(G).where(G.user_id == user_id, G.id == gap_id))

    async def delete_many(self, user_id: uuid.UUID, gap_ids: Sequence[uuid.UUID]) -> None:
        if gap_ids:
            await self._db.execute(delete(G).where(G.user_id == user_id, G.id.in_(gap_ids)))

    async def evidence_for(self, user_id: uuid.UUID, gap_ids: Sequence[uuid.UUID]) -> list[E]:
        if not gap_ids:
            return []
        rows = await self._db.execute(
            select(E)
            .where(E.user_id == user_id, E.gap_id.in_(gap_ids))
            .order_by(E.evidence_role, E.id)
        )
        return list(rows.scalars())
