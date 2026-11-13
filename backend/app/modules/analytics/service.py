"""Learning analytics service (Phase 5 M5; spec 2.6, 3, 5.4; D-108, D-111).

Everything is derived on request from the caller's own attempts, reviews and sessions. Dates are the
user's local days. Nothing here invents data: an empty account returns zeros and nulls.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.localtime import day_bounds, day_start_utc, local_date, user_zone
from app.models.user import User
from app.modules.analytics.logic import (
    Thresholds,
    TopicStat,
    compute_streaks,
    compute_topics,
)
from app.repositories.analytics_repository import AnalyticsRepository, Window
from app.repositories.revision_repository import RevisionRepository

MAX_RANGE_DAYS = 731
STATUS_LABELS = {
    "strong": "Strong",
    "developing": "Developing",
    "needs_revision": "May need revision",
    "not_enough_data": "Not enough data",
}
TOPIC_NOTE = (
    "Labels are estimates from your quiz answers and the thresholds shown here. They are not a "
    "measure of how well you know a topic."
)
OVERVIEW_NOTE = (
    "Figures come from your own quiz attempts, flashcard reviews and revision sessions. Quiz "
    "scores are one signal among several and do not measure mastery."
)
QUIZ_NOTE = (
    "A rising score can reflect having seen the questions before. Use it together with spaced "
    "revision, not as proof of retention."
)


def _now() -> datetime:
    return datetime.now(UTC)


def _bad_range(message: str) -> HTTPException:
    return HTTPException(422, detail={"code": "VALIDATION_ERROR", "message": message})


class AnalyticsService:
    def __init__(self, db: AsyncSession, settings: Settings) -> None:
        self._db = db
        self._s = settings
        self._repo = AnalyticsRepository(db)
        self._revision = RevisionRepository(db)

    @property
    def thresholds(self) -> Thresholds:
        s = self._s
        return Thresholds(
            strong_at=s.analytics_strong_at,
            needs_revision_below=s.analytics_needs_revision_below,
            min_answers=s.analytics_min_answers,
            recent_attempts=s.analytics_recent_attempts,
            trend_delta=s.analytics_trend_delta,
        )

    # dates ───────────────────────────────────────────────────────────────────

    def resolve_range(
        self,
        zone: ZoneInfo,
        start: date | None,
        end: date | None,
        *,
        default_days: int | None,
    ) -> tuple[date | None, date | None]:
        """The user's local date range. `default_days` fills a missing start with a recent window
        (the end defaults to today); None means all time."""
        today = local_date(zone, _now())
        if end is None and default_days is not None:
            end = max(today, start) if start is not None else today
        if start is None and default_days is not None and end is not None:
            start = end - timedelta(days=default_days - 1)
        if start is not None and end is not None:
            if end < start:
                raise _bad_range("end_date must not be before start_date.")
            if (end - start).days >= MAX_RANGE_DAYS:
                raise _bad_range(f"The date range can be at most {MAX_RANGE_DAYS} days.")
        return start, end

    @staticmethod
    def window(zone: ZoneInfo, start: date | None, end: date | None) -> Window:
        return (
            day_start_utc(zone, start) if start is not None else None,
            day_start_utc(zone, end + timedelta(days=1)) if end is not None else None,
        )

    # overview ────────────────────────────────────────────────────────────────

    async def overview(
        self,
        user: User,
        *,
        subject_id: uuid.UUID | None,
        chapter_id: uuid.UUID | None,
        start: date | None,
        end: date | None,
    ) -> dict[str, Any]:
        zone = user_zone(user)
        start, end = self.resolve_range(zone, start, end, default_days=None)
        win = self.window(zone, start, end)
        now = _now()
        day_start, day_end = day_bounds(zone, now)
        quiz = await self._repo.quiz_totals(user.id, subject_id, chapter_id, win)
        reviews = await self._repo.review_totals(user.id, subject_id, chapter_id, win)
        sessions = await self._repo.session_totals(user.id, subject_id, chapter_id, win)
        topics = await self.topics(user, subject_id=subject_id, chapter_id=chapter_id, window=win)
        counts = await self._revision.counts(
            user.id,
            day_start=day_start,
            day_end=day_end,
            subject_id=subject_id,
            chapter_id=chapter_id,
        )
        today_reviews = await self._revision.reviewed_between(
            user.id, day_start, day_end, subject_id=subject_id, chapter_id=chapter_id
        )
        today_quizzes = sum(
            (
                await self._repo.per_day_quiz(
                    user.id, zone.key, subject_id, chapter_id, (day_start, day_end)
                )
            ).values()
        )
        streak = compute_streaks(
            await self._repo.active_dates(user.id, zone.key), local_date(zone, now)
        )
        return {
            "quizzes_attempted": quiz["quizzes"],
            "quiz_attempts": quiz["attempts"],
            "average_quiz_percentage": quiz["average_percentage"],
            "flashcards_reviewed": reviews["reviews"],
            "distinct_cards_reviewed": reviews["cards"],
            "revision_sessions": sessions["sessions"],
            "time_spent_seconds": quiz["time_seconds"] + sessions["time_seconds"],
            "quiz_time_seconds": quiz["time_seconds"],
            "revision_time_seconds": sessions["time_seconds"],
            "current_streak_days": streak[0],
            "longest_streak_days": streak[1],
            "due_today": counts["due"],
            "overdue": counts["overdue"],
            "topics_needing_attention": sum(1 for t in topics if t.status == "needs_revision"),
            "reviews_today": today_reviews,
            "quiz_attempts_today": int(today_quizzes),
            "timezone": zone.key,
            "note": OVERVIEW_NOTE,
        }

    # quizzes ─────────────────────────────────────────────────────────────────

    async def quiz_performance(
        self,
        user: User,
        *,
        subject_id: uuid.UUID | None,
        chapter_id: uuid.UUID | None,
        start: date | None,
        end: date | None,
        limit: int,
    ) -> dict[str, Any]:
        zone = user_zone(user)
        start, end = self.resolve_range(zone, start, end, default_days=None)
        win = self.window(zone, start, end)
        rows = await self._repo.quiz_points(user.id, subject_id, chapter_id, win, limit)
        totals = await self._repo.quiz_totals(user.id, subject_id, chapter_id, win)
        points = []
        for attempt, quiz in rows:
            assert attempt.submitted_at is not None
            points.append(
                {
                    "attempt_id": attempt.id,
                    "quiz_id": attempt.quiz_id,
                    "quiz_title": quiz.title,
                    "submitted_at": attempt.submitted_at,
                    "local_date": local_date(zone, attempt.submitted_at),
                    "percentage": float(attempt.percentage)
                    if attempt.percentage is not None
                    else None,
                    "score": float(attempt.score) if attempt.score is not None else None,
                    "max_score": float(attempt.max_score)
                    if attempt.max_score is not None
                    else None,
                    "evaluation_status": attempt.evaluation_status,
                }
            )
        return {
            "points": points,
            "attempts": totals["attempts"],
            "average_percentage": totals["average_percentage"],
            "note": QUIZ_NOTE,
        }

    async def subject_performance(
        self,
        user: User,
        *,
        subject_id: uuid.UUID | None,
        chapter_id: uuid.UUID | None,
        start: date | None,
        end: date | None,
    ) -> list[dict[str, Any]]:
        zone = user_zone(user)
        start, end = self.resolve_range(zone, start, end, default_days=None)
        win = self.window(zone, start, end)
        quiz = await self._repo.subject_quiz(user.id, subject_id, chapter_id, win)
        reviews = await self._repo.reviews_by_subject(user.id, subject_id, chapter_id, win)
        keys = {*quiz, *reviews}
        names = await self._repo.subject_names(user.id, [k for k in keys if k is not None])
        items = []
        for key in keys:
            q = quiz.get(key, {})
            counts = reviews.get(key, {})
            total = sum(counts.values())
            hard = counts.get("again", 0) + counts.get("hard", 0)
            items.append(
                {
                    "subject_id": key,
                    "subject_name": names.get(key) if key is not None else None,
                    "quiz_attempts": q.get("attempts", 0),
                    "average_quiz_percentage": q.get("average_percentage"),
                    "last_attempt_at": q.get("last_attempt_at"),
                    "reviews": total,
                    "hard_or_again_share": round(hard / total, 3) if total else None,
                }
            )
        items.sort(
            key=lambda i: (i["subject_name"] is None, str(i["subject_name"] or "").casefold())
        )
        return items

    # topics ──────────────────────────────────────────────────────────────────

    async def topics(
        self,
        user: User,
        *,
        subject_id: uuid.UUID | None,
        chapter_id: uuid.UUID | None,
        window: Window,
    ) -> list[TopicStat]:
        rows = await self._repo.topic_attempt_rows(
            user.id, subject_id, chapter_id, window, self._s.analytics_max_attempts
        )
        return compute_topics(rows, self.thresholds)

    async def topic_performance(
        self,
        user: User,
        *,
        subject_id: uuid.UUID | None,
        chapter_id: uuid.UUID | None,
        start: date | None,
        end: date | None,
    ) -> list[TopicStat]:
        zone = user_zone(user)
        start, end = self.resolve_range(zone, start, end, default_days=None)
        return await self.topics(
            user, subject_id=subject_id, chapter_id=chapter_id, window=self.window(zone, start, end)
        )

    # revision activity, calendar, streaks ────────────────────────────────────

    async def revision_activity(
        self,
        user: User,
        *,
        subject_id: uuid.UUID | None,
        chapter_id: uuid.UUID | None,
        start: date | None,
        end: date | None,
    ) -> dict[str, Any]:
        zone = user_zone(user)
        start, end = self.resolve_range(zone, start, end, default_days=30)
        assert start is not None and end is not None
        win = self.window(zone, start, end)
        per_day = await self._repo.per_day_reviews(user.id, zone.key, subject_id, chapter_id, win)
        sessions = await self._repo.per_day_sessions(user.id, zone.key, subject_id, chapter_id, win)
        ratings = await self._repo.rating_counts(user.id, subject_id, chapter_id, win)
        totals = await self._repo.review_totals(user.id, subject_id, chapter_id, win)
        days = []
        for day in sorted({*per_day, *sessions}):
            r = per_day.get(day, {})
            days.append(
                {
                    "date": day,
                    "reviews": sum(r.values()),
                    "again": r.get("again", 0),
                    "hard": r.get("hard", 0),
                    "good": r.get("good", 0),
                    "easy": r.get("easy", 0),
                    "sessions": sessions.get(day, 0),
                }
            )
        return {
            "days": days,
            "total_reviews": totals["reviews"],
            "rating_distribution": {
                k: ratings.get(k, 0) for k in ("again", "hard", "good", "easy")
            },
            "average_response_ms": totals["average_response_ms"],
            "start_date": start,
            "end_date": end,
            "timezone": zone.key,
        }

    async def streaks(self, user: User) -> dict[str, Any]:
        zone = user_zone(user)
        dates = await self._repo.active_dates(user.id, zone.key)
        current, longest, last = compute_streaks(dates, local_date(zone, _now()))
        if not dates:
            message = (
                "No study activity yet. Whenever you are ready, a quiz or a few cards is enough."
            )
        elif current:
            message = f"You have studied on {current} day{'s' if current != 1 else ''} in a row."
        else:
            message = "Pick up whenever suits you. Your longest streak and history stay here."
        return {
            "current_streak_days": current,
            "longest_streak_days": longest,
            "last_active_date": last,
            "active_days_total": len(set(dates)),
            "message": message,
        }

    async def calendar(
        self,
        user: User,
        *,
        subject_id: uuid.UUID | None,
        chapter_id: uuid.UUID | None,
        start: date | None,
        end: date | None,
    ) -> dict[str, Any]:
        zone = user_zone(user)
        start, end = self.resolve_range(zone, start, end, default_days=90)
        assert start is not None and end is not None
        win = self.window(zone, start, end)
        quizzes = await self._repo.per_day_quiz(user.id, zone.key, subject_id, chapter_id, win)
        sessions = await self._repo.per_day_sessions(user.id, zone.key, subject_id, chapter_id, win)
        reviews = await self._repo.per_day_reviews(user.id, zone.key, subject_id, chapter_id, win)
        days = []
        for day in sorted({*quizzes, *sessions, *reviews}):
            q, s, r = quizzes.get(day, 0), sessions.get(day, 0), sum(reviews.get(day, {}).values())
            days.append(
                {
                    "date": day,
                    "quiz_attempts": q,
                    "revision_sessions": s,
                    "reviews": r,
                    "activities": q + s,
                }
            )
        return {
            "days": days,
            "streak": await self.streaks(user),
            "start_date": start,
            "end_date": end,
            "timezone": zone.key,
        }

    async def day_detail(self, user: User, day: date) -> dict[str, Any]:
        zone = user_zone(user)
        start = day_start_utc(zone, day)
        end = day_start_utc(zone, day + timedelta(days=1))
        attempts = await self._repo.day_quiz_attempts(user.id, start, end)
        sessions = await self._repo.day_sessions(user.id, start, end)
        ratings = (
            await self._repo.per_day_reviews(user.id, zone.key, None, None, (start, end))
        ).get(day, {})
        return {
            "date": day,
            "quizzes": [
                {
                    "attempt_id": a.id,
                    "quiz_id": a.quiz_id,
                    "quiz_title": q.title,
                    "submitted_at": a.submitted_at,
                    "percentage": float(a.percentage) if a.percentage is not None else None,
                    "time_taken_seconds": a.time_taken_seconds,
                }
                for a, q in attempts
            ],
            "sessions": [
                {
                    "session_id": s.id,
                    "completed_at": s.completed_at,
                    "reviewed_cards": s.reviewed_cards,
                    "total_cards": s.total_cards,
                    "duration_seconds": s.duration_seconds,
                }
                for s in sessions
            ],
            "reviews": sum(ratings.values()),
            "rating_distribution": {
                k: ratings.get(k, 0) for k in ("again", "hard", "good", "easy")
            },
            "timezone": zone.key,
        }
