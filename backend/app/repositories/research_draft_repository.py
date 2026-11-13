"""Persistence for drafts and their versions (Phase 7 M7.9). Scoped by `user_id` (rule 3)."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research import ResearchDraft, ResearchDraftVersion

D = ResearchDraft
V = ResearchDraftVersion
MAX_VERSIONS = 200


class ResearchDraftRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get(self, user_id: uuid.UUID, draft_id: uuid.UUID) -> D | None:
        return (
            await self._db.execute(select(D).where(D.user_id == user_id, D.id == draft_id))
        ).scalar_one_or_none()

    async def list_for_project(
        self,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        *,
        status: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[D], int]:
        where = [D.user_id == user_id, D.research_project_id == project_id]
        if status:
            where.append(D.status == status)
        total = (await self._db.execute(select(func.count(D.id)).where(*where))).scalar_one()
        rows = (
            await self._db.execute(
                select(D)
                .where(*where)
                .order_by(D.updated_at.desc(), D.id)
                .limit(limit)
                .offset(offset)
            )
        ).scalars()
        return list(rows), total

    async def add(self, draft: D) -> D:
        self._db.add(draft)
        await self._db.flush()
        return draft

    async def delete(self, user_id: uuid.UUID, draft_id: uuid.UUID) -> None:
        await self._db.execute(delete(D).where(D.user_id == user_id, D.id == draft_id))

    async def add_version(self, version: V) -> V:
        self._db.add(version)
        await self._db.flush()
        await self._db.execute(
            delete(V).where(
                V.user_id == version.user_id,
                V.draft_id == version.draft_id,
                V.version_number <= version.version_number - MAX_VERSIONS,
            )
        )
        return version

    async def versions(self, user_id: uuid.UUID, draft_id: uuid.UUID) -> list[V]:
        rows = await self._db.execute(
            select(V)
            .where(V.user_id == user_id, V.draft_id == draft_id)
            .order_by(V.version_number.desc())
        )
        return list(rows.scalars())

    async def version(self, user_id: uuid.UUID, draft_id: uuid.UUID, number: int) -> V | None:
        return (
            await self._db.execute(
                select(V).where(
                    V.user_id == user_id, V.draft_id == draft_id, V.version_number == number
                )
            )
        ).scalar_one_or_none()
