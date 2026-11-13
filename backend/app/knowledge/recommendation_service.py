"""Learner recommendations stored in the Phase 5 `revision_recommendations` table (Milestone 6.8).

Same lifecycle as Phase 5: the pending set is made to match the current rules, completed or
dismissed items do not return for COOLDOWN_DAYS, and ids are owner-scoped (a foreign id is a 404).
Phase 5 rows (`source = phase5_rule`) are never touched here, and the Phase 5 endpoints never see
these."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.recommendations import MAX_ITEMS, rank
from app.models.revision import RevisionRecommendation
from app.modules.recommendations.service import COOLDOWN_DAYS, RecommendationNotFoundError
from app.repositories.learner_recommendation_repository import LearnerRecommendationRepository
from app.repositories.recommendation_repository import LEARNER, RecommendationRepository


def _now() -> datetime:
    return datetime.now(UTC)


class LearnerRecommendationService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._facts = LearnerRecommendationRepository(db)
        self._repo = RecommendationRepository(db)

    async def sync(self, user_id: uuid.UUID) -> list[RevisionRecommendation]:
        now = _now()
        candidates = rank(
            await self._facts.concepts(user_id),
            await self._facts.misconceptions(user_id),
            await self._facts.edges(user_id),
            now,
        )
        wanted = {c.dedupe_key: c for c in candidates}
        existing = {r.dedupe_key: r for r in await self._repo.pending(user_id, LEARNER)}
        await self._repo.delete_stale(
            user_id, [r.id for k, r in existing.items() if k not in wanted]
        )
        cooling = await self._repo.recently_resolved_keys(
            user_id, now - timedelta(days=COOLDOWN_DAYS), LEARNER
        )
        for key, c in wanted.items():
            fields: dict[str, Any] = {
                "reason": c.reason,
                "priority": c.priority,
                "score": Decimal(str(c.score)),
                "suggested_action": c.action,
                "evidence": c.evidence,
                "knowledge_node_id": c.node_id,
                "topic_name": c.topic_name,
            }
            if key in existing:
                await self._repo.refresh(user_id, existing[key].id, **fields)
            elif key not in cooling:
                await self._repo.insert_pending(
                    user_id,
                    {
                        "recommendation_type": c.type,
                        "dedupe_key": key,
                        "source": LEARNER,
                        **fields,
                    },
                )
        await self._db.commit()
        rows = await self._repo.pending(user_id, LEARNER)
        rows.sort(key=lambda r: (-(r.score or Decimal(0)), r.topic_name or "", r.id))
        return rows[:MAX_ITEMS]

    async def resolve(
        self, user_id: uuid.UUID, rec_id: uuid.UUID, status: str
    ) -> RevisionRecommendation:
        rec = await self._repo.get(user_id, rec_id)
        if rec is None or rec.source != LEARNER:
            raise RecommendationNotFoundError
        if rec.status == "pending":
            await self._repo.resolve(user_id, rec_id, status, _now())
            await self._db.commit()
            rec = await self._repo.get(user_id, rec_id)
            assert rec is not None
        return rec
