"""Rule-based revision recommendations (Phase 5 M6; spec 2.8, 5.5).

Transparent rules, highest priority first: overdue cards, repeatedly failed topics, low topic
performance, cards due today, topics not practised recently. Every reason is built from real counts
and percentages; nothing is invented and no model is involved. Dismissed or completed items do not
come back for `COOLDOWN_DAYS`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.localtime import day_bounds, user_zone
from app.models.revision import RevisionRecommendation
from app.models.user import User
from app.modules.analytics.logic import TopicStat
from app.modules.analytics.service import AnalyticsService
from app.repositories.analytics_repository import AnalyticsRepository
from app.repositories.recommendation_repository import RecommendationRepository
from app.repositories.revision_repository import RevisionRepository
from app.study.errors import StudyError

COOLDOWN_DAYS = 7
STALE_AFTER_DAYS = 14
STRUGGLE_MIN_AGAIN = 3
MAX_ITEMS = 10
RANK = {"high": 0, "medium": 1, "low": 2}


class RecommendationNotFoundError(StudyError):
    code = "RESOURCE_NOT_FOUND"
    http_status = 404
    user_message = "Recommendation not found."


def _now() -> datetime:
    return datetime.now(UTC)


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


class RecommendationService:
    def __init__(self, db: AsyncSession, settings: Settings) -> None:
        self._db = db
        self._analytics = AnalyticsService(db, settings)
        self._repo = RecommendationRepository(db)
        self._data = AnalyticsRepository(db)
        self._revision = RevisionRepository(db)

    async def _topics(self, user: User) -> list[TopicStat]:
        return await self._analytics.topics(
            user, subject_id=None, chapter_id=None, window=(None, None)
        )

    async def candidates(self, user: User) -> list[dict[str, Any]]:
        now = _now()
        day_start, day_end = day_bounds(user_zone(user), now)
        counts = await self._revision.counts(
            user.id, day_start=day_start, day_end=day_end, subject_id=None, chapter_id=None
        )
        out: list[dict[str, Any]] = []
        if counts["overdue"]:
            out.append(
                {
                    "recommendation_type": "flashcard",
                    "dedupe_key": "cards-overdue",
                    "priority": "high",
                    "topic_name": None,
                    "reason": f"{_plural(counts['overdue'], 'flashcard')} overdue for review. "
                    "Reviewing them soon helps you keep what you learned.",
                }
            )
        stats = await self._topics(user)
        struggle = await self._data.struggle_by_topic(user.id, (None, None))
        for topic, s in sorted(struggle.items()):
            if s["again"] >= STRUGGLE_MIN_AGAIN:
                out.append(
                    {
                        "recommendation_type": "topic",
                        "dedupe_key": f"struggle:{topic.casefold()}"[:160],
                        "priority": "high",
                        "topic_name": topic[:120],
                        "reason": f"You rated {s['again']} of {_plural(s['reviews'], 'review')} "
                        f"on {topic} flashcards as Again. Practise the questions you previously "
                        "got wrong.",
                    }
                )
        for st in stats:
            if st.status == "needs_revision" and st.accuracy is not None:
                out.append(
                    {
                        "recommendation_type": "topic",
                        "dedupe_key": f"weak:{st.topic.casefold()}"[:160],
                        "priority": "high" if st.accuracy < 40 else "medium",
                        "topic_name": st.topic[:120],
                        "reason": f"Your quiz accuracy on {st.topic} is {st.accuracy:.0f}% "
                        f"across {_plural(st.answers, 'answer')}. Consider revising it and "
                        "attempting another quiz.",
                    }
                )
        today_only = counts["due"] - counts["overdue"]
        if today_only > 0:
            out.append(
                {
                    "recommendation_type": "flashcard",
                    "dedupe_key": "cards-due-today",
                    "priority": "medium",
                    "topic_name": None,
                    "reason": f"{_plural(today_only, 'flashcard')} due for review today.",
                }
            )
        cutoff = now - timedelta(days=STALE_AFTER_DAYS)
        for st in stats:
            if (
                st.status in ("developing", "needs_revision")
                and st.last_attempt_at is not None
                and st.last_attempt_at < cutoff
            ):
                out.append(
                    {
                        "recommendation_type": "topic",
                        "dedupe_key": f"stale:{st.topic.casefold()}"[:160],
                        "priority": "low",
                        "topic_name": st.topic[:120],
                        "reason": f"You have not practised {st.topic} for "
                        f"{_plural((now - st.last_attempt_at).days, 'day')}.",
                    }
                )
        return out

    async def sync(self, user: User) -> list[RevisionRecommendation]:
        """Make the pending set match the current rules, then return it ordered by priority."""
        now = _now()
        wanted = {c["dedupe_key"]: c for c in await self.candidates(user)}
        existing = {r.dedupe_key: r for r in await self._repo.pending(user.id)}
        await self._repo.delete_stale(
            user.id, [r.id for k, r in existing.items() if k not in wanted]
        )
        cooling = await self._repo.recently_resolved_keys(
            user.id, now - timedelta(days=COOLDOWN_DAYS)
        )
        for key, cand in wanted.items():
            if key in existing:
                await self._repo.refresh(
                    user.id, existing[key].id, reason=cand["reason"], priority=cand["priority"]
                )
            elif key not in cooling:
                await self._repo.insert_pending(user.id, cand)
        await self._db.commit()
        rows = await self._repo.pending(user.id)
        rows.sort(key=lambda r: (RANK[r.priority], r.created_at))
        return rows[:MAX_ITEMS]

    async def weak_topics(self, user: User) -> list[dict[str, Any]]:
        stats = await self._topics(user)
        return [
            {"topic": s.topic, "accuracy": s.accuracy, "answers": s.answers, "trend": s.trend}
            for s in stats
            if s.status == "needs_revision"
        ]

    async def resolve(self, user: User, rec_id: uuid.UUID, status: str) -> RevisionRecommendation:
        rec = await self._repo.get(user.id, rec_id)
        if rec is None or rec.source != "phase5_rule":  # learner ones use /recommendations/learner
            raise RecommendationNotFoundError
        if rec.status == "pending":
            await self._repo.resolve(user.id, rec_id, status, _now())
            await self._db.commit()
            rec = await self._repo.get(user.id, rec_id)
            assert rec is not None
        return rec
