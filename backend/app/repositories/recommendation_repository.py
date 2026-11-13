"""Revision recommendation persistence (Phase 5 M6). Every query filters by `user_id`."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.revision import RevisionRecommendation as Rec

PHASE5 = "phase5_rule"
LEARNER = "learner_rule"


class RecommendationRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def pending(self, user_id: uuid.UUID, source: str = PHASE5) -> list[Rec]:
        stmt = select(Rec).where(
            Rec.user_id == user_id, Rec.status == "pending", Rec.source == source
        )
        return list((await self._db.execute(stmt)).scalars().all())

    async def get(self, user_id: uuid.UUID, rec_id: uuid.UUID) -> Rec | None:
        stmt = select(Rec).where(Rec.user_id == user_id, Rec.id == rec_id)
        return (await self._db.execute(stmt)).scalar_one_or_none()

    async def recently_resolved_keys(
        self, user_id: uuid.UUID, since: datetime, source: str = PHASE5
    ) -> set[str]:
        stmt = select(Rec.dedupe_key).where(
            Rec.user_id == user_id,
            Rec.status != "pending",
            Rec.completed_at >= since,
            Rec.source == source,
        )
        return set((await self._db.execute(stmt)).scalars().all())

    async def insert_pending(self, user_id: uuid.UUID, values: dict[str, Any]) -> None:
        stmt = (
            insert(Rec)
            .values(user_id=user_id, status="pending", **values)
            .on_conflict_do_nothing(
                index_elements=["user_id", "dedupe_key"], index_where=Rec.status == "pending"
            )
        )
        await self._db.execute(stmt)

    async def refresh(
        self,
        user_id: uuid.UUID,
        rec_id: uuid.UUID,
        *,
        reason: str,
        priority: str,
        **extra: Any,
    ) -> None:
        await self._db.execute(
            update(Rec)
            .where(Rec.user_id == user_id, Rec.id == rec_id, Rec.status == "pending")
            .values(reason=reason, priority=priority, **extra)
        )

    async def delete_stale(self, user_id: uuid.UUID, ids: list[uuid.UUID]) -> None:
        if ids:
            await self._db.execute(
                delete(Rec).where(Rec.user_id == user_id, Rec.id.in_(ids), Rec.status == "pending")
            )

    async def resolve(
        self, user_id: uuid.UUID, rec_id: uuid.UUID, status: str, now: datetime
    ) -> None:
        await self._db.execute(
            update(Rec)
            .where(Rec.user_id == user_id, Rec.id == rec_id, Rec.status == "pending")
            .values(status=status, completed_at=now)
        )
