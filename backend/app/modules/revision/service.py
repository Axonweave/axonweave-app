"""Spaced repetition service (Phase 5 M3; spec 2.3, 2.5, 5.2, 5.3; D-105 to D-114).

Rules:
* Ownership first on every path: a foreign or missing card or session is a 404.
* Scheduling rows are created lazily for the user's flashcards. Scheduling maths is only in
  `FsrsScheduler` (pure); this service passes `now` and stores the result.
* A review is one transaction: lock the card's scheduling row, apply the rating, update the row and
  append the event with the previous and resulting state. The idempotency key makes a retried
  request return the stored event instead of reviewing twice.
* "Today" is the user's local day (D-111); all timestamps are UTC.
* Logs carry ids, ratings and counts only: never card text.
"""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.localtime import day_bounds, day_start_utc, local_date, user_zone
from app.core.rate_limit import get_rate_limiter
from app.models.flashcard import Flashcard
from app.models.revision import FlashcardReview, FlashcardScheduling, RevisionSession
from app.models.study_material import StudyMaterial
from app.models.user import User
from app.modules.revision.errors import (
    CardNotFoundError,
    CardNotInSessionError,
    CardSuspendedError,
    InvalidStateError,
    NothingDueError,
    ReviewRateLimitedError,
    SessionNotActiveError,
    SessionNotFoundError,
)
from app.modules.revision.fsrs_scheduler import (
    CardState,
    FsrsScheduler,
    Rating,
    SchedulerConfig,
    SchedulerError,
)
from app.repositories.revision_repository import RevisionRepository, Row
from app.study.errors import IdempotencyKeyReusedError

logger = structlog.get_logger()
UPCOMING_DAYS = 7
RECENT_REVIEWS = 5


def _now() -> datetime:
    return datetime.now(UTC)


def state_of(row: FlashcardScheduling) -> CardState:
    return CardState(
        state=row.state,
        due=row.due_at,
        step=row.step,
        stability=row.stability,
        difficulty=row.difficulty,
        last_review=row.last_review_at,
        repetitions=row.repetitions,
        lapses=row.lapses,
    )


class RevisionService:
    def __init__(self, db: AsyncSession, settings: Settings) -> None:
        self._db = db
        self._s = settings
        self._repo = RevisionRepository(db)
        self._scheduler = FsrsScheduler(
            SchedulerConfig(desired_retention=settings.revision_desired_retention)
        )

    @property
    def scheduler(self) -> FsrsScheduler:
        return self._scheduler

    @property
    def retention(self) -> float:
        return self._scheduler.config.desired_retention

    async def _ensure(self, user: User) -> None:
        if await self._repo.ensure_scheduling(user.id, self._scheduler.version):
            await self._db.commit()

    def retrievability(self, row: FlashcardScheduling, now: datetime) -> float | None:
        try:
            value = self._scheduler.retrievability(state_of(row), now)
        except SchedulerError:
            return None
        return None if value is None else round(value, 4)

    # lists and summary ───────────────────────────────────────────────────────

    async def list_cards(
        self,
        user: User,
        *,
        bucket: str,
        subject_id: uuid.UUID | None,
        chapter_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Row], int, datetime, datetime, datetime, str]:
        await self._ensure(user)
        now = _now()
        zone = user_zone(user)
        start, end = day_bounds(zone, now)
        rows, total = await self._repo.list_cards(
            user.id,
            bucket=bucket,
            day_start=start,
            day_end=end,
            subject_id=subject_id,
            chapter_id=chapter_id,
            limit=limit,
            offset=offset,
        )
        return rows, total, now, start, end, zone.key

    async def summary(
        self, user: User, *, subject_id: uuid.UUID | None, chapter_id: uuid.UUID | None
    ) -> dict[str, Any]:
        await self._ensure(user)
        now = _now()
        zone = user_zone(user)
        start, end = day_bounds(zone, now)
        counts = await self._repo.counts(
            user.id, day_start=start, day_end=end, subject_id=subject_id, chapter_id=chapter_id
        )
        reviewed = await self._repo.reviewed_between(
            user.id, start, end, subject_id=subject_id, chapter_id=chapter_id
        )
        started_new = await self._repo.new_cards_started_between(user.id, start, end)
        today = local_date(zone, now)
        horizon = day_start_utc(zone, today + timedelta(days=1 + UPCOMING_DAYS))
        per_day = await self._repo.upcoming(
            user.id, zone.key, end, horizon, subject_id=subject_id, chapter_id=chapter_id
        )
        upcoming = [
            {"date": today + timedelta(days=i), "count": per_day.get(today + timedelta(days=i), 0)}
            for i in range(1, 1 + UPCOMING_DAYS)
        ]
        planned = reviewed + counts["due"]
        subjects = await self._repo.subject_breakdown(user.id, day_end=end)
        recent = await self._repo.recent_reviews(user.id, RECENT_REVIEWS)
        return {
            "total_cards": counts["total"],
            "due_today": counts["due"],
            "overdue": counts["overdue"],
            "new": counts["new"],
            "learning": counts["learning"],
            "review": counts["review"],
            "suspended": counts["suspended"],
            "reviewed_today": reviewed,
            "daily_completion": round(reviewed / planned, 4) if planned else None,
            "new_cards_remaining_today": max(0, self._s.revision_new_cards_per_day - started_new),
            "upcoming": upcoming,
            "subjects": subjects,
            "recent": [
                {"card_id": r.flashcard_id, "rating": r.rating, "reviewed_at": r.reviewed_at}
                for r in recent
            ],
            "timezone": zone.key,
            "desired_retention": self.retention,
        }

    # one card ────────────────────────────────────────────────────────────────

    async def _card(self, user: User, card_id: uuid.UUID) -> Row:
        if not await self._repo.card_exists(card_id, user.id):
            raise CardNotFoundError
        await self._ensure(user)
        row = await self._repo.owned_card(card_id, user.id)
        if row is None:
            raise CardNotFoundError
        return row

    async def schedule(self, user: User, card_id: uuid.UUID) -> FlashcardScheduling:
        _, sched, _ = await self._card(user, card_id)
        return sched

    async def set_suspended(
        self, user: User, card_id: uuid.UUID, suspended: bool
    ) -> FlashcardScheduling:
        await self._card(user, card_id)
        locked = await self._repo.locked_card(card_id, user.id)
        if locked is None:
            raise CardNotFoundError
        sched = locked[1]
        if sched.suspended != suspended:
            sched.suspended = suspended
            sched.version += 1
        await self._db.commit()
        return sched

    async def history(
        self, user: User, card_id: uuid.UUID, limit: int, offset: int
    ) -> tuple[list[FlashcardReview], int]:
        if not await self._repo.card_exists(card_id, user.id):
            raise CardNotFoundError
        return await self._repo.reviews_for_card(card_id, user.id, limit, offset)

    # review ──────────────────────────────────────────────────────────────────

    async def _limit(self, user: User) -> None:
        try:
            await get_rate_limiter().check(
                f"revision:review:{user.id}", self._s.revision_reviews_per_minute_per_user, 60
            )
        except HTTPException:
            raise ReviewRateLimitedError from None

    async def review(
        self,
        user: User,
        card_id: uuid.UUID,
        *,
        rating: str,
        idempotency_key: str,
        response_time_ms: int | None,
        session_id: uuid.UUID | None,
    ) -> tuple[FlashcardReview, FlashcardScheduling, bool]:
        """Apply one rating. Returns (event, new schedule, duplicate)."""
        await self._limit(user)
        await self._card(user, card_id)  # ownership first: foreign or missing is a 404
        existing = await self._repo.review_by_key(user.id, idempotency_key)
        if existing is not None:
            return await self._duplicate(user, existing, card_id)

        locked = await self._repo.locked_card(card_id, user.id)
        if locked is None:
            raise CardNotFoundError
        sched = locked[1]
        # A concurrent request with the same key may have finished while we waited for the lock.
        existing = await self._repo.review_by_key(user.id, idempotency_key)
        if existing is not None:
            await self._db.commit()
            return await self._duplicate(user, existing, card_id)
        if sched.suspended:
            await self._db.rollback()
            raise CardSuspendedError

        session: RevisionSession | None = None
        first_in_session = False
        if session_id is not None:
            session = await self._repo.get_session(session_id, user.id, lock=True)
            if session is None:
                await self._db.rollback()
                raise SessionNotFoundError
            if session.status != "active":
                await self._db.rollback()
                raise SessionNotActiveError
            if str(card_id) not in session.card_ids:
                await self._db.rollback()
                raise CardNotInSessionError
            first_in_session = not await self._repo.session_has_review(session.id, card_id, user.id)

        now = _now()
        previous = state_of(sched)
        if previous.last_review is not None and now < previous.last_review:
            now = previous.last_review  # clock skew: never review "before" the last review
        try:
            outcome = self._scheduler.review(
                previous, Rating(rating), now, response_time_ms=response_time_ms
            )
        except SchedulerError:
            await self._db.rollback()
            raise InvalidStateError from None
        new = outcome.state
        sched.state = new.state
        sched.step = new.step
        sched.due_at = new.due
        sched.stability = new.stability
        sched.difficulty = new.difficulty
        sched.last_review_at = new.last_review
        sched.repetitions = new.repetitions
        sched.lapses = new.lapses
        sched.elapsed_days = outcome.elapsed_days
        sched.scheduled_days = outcome.scheduled_days
        sched.scheduler_version = self._scheduler.version
        sched.version += 1
        event = FlashcardReview(
            user_id=user.id,
            flashcard_id=card_id,
            session_id=session.id if session is not None else None,
            idempotency_key=idempotency_key,
            rating=rating,
            reviewed_at=now,
            elapsed_days=outcome.elapsed_days,
            scheduled_days=outcome.scheduled_days,
            response_time_ms=response_time_ms,
            previous_state=previous.to_json(),
            resulting_state=new.to_json(),
            scheduler_version=self._scheduler.version,
        )
        try:
            await self._repo.add_review(event)
            if session is not None:
                await self._repo.bump_session(
                    session.id, user.id, now, reviewed=1 if first_in_session else 0
                )
            await self._db.commit()
        except IntegrityError:  # the same key won a race: return its stored event
            await self._db.rollback()
            winner = await self._repo.review_by_key(user.id, idempotency_key)
            if winner is None:
                raise
            return await self._duplicate(user, winner, card_id)
        logger.info("flashcard_reviewed", card_id=str(card_id), rating=rating)
        return event, sched, False

    async def _duplicate(
        self, user: User, event: FlashcardReview, card_id: uuid.UUID
    ) -> tuple[FlashcardReview, FlashcardScheduling, bool]:
        if event.flashcard_id != card_id:  # one key, one review: not reusable on another card
            raise IdempotencyKeyReusedError
        row = await self._repo.owned_card(card_id, user.id)
        if row is None:
            raise CardNotFoundError
        return event, row[1], True

    # sessions ────────────────────────────────────────────────────────────────

    async def start_session(
        self,
        user: User,
        *,
        subject_id: uuid.UUID | None,
        chapter_id: uuid.UUID | None,
        limit: int | None,
        include_new: bool,
    ) -> tuple[RevisionSession, bool]:
        """A new session over the due cards (then new ones up to the daily cap), or the active one
        (resume). A session idle for too long is closed as abandoned first (D-114)."""
        await self._ensure(user)
        now = _now()
        active = await self._repo.active_session(user.id, lock=True)
        if active is not None:
            idle = timedelta(minutes=self._s.revision_session_idle_minutes)
            if now - active.last_activity_at <= idle:
                await self._db.commit()
                return active, True
            active.status = "abandoned"
            await self._db.commit()
        zone = user_zone(user)
        start, end = day_bounds(zone, now)
        started_new = await self._repo.new_cards_started_between(user.id, start, end)
        new_room = max(0, self._s.revision_new_cards_per_day - started_new) if include_new else 0
        size = min(limit or self._s.revision_session_max_cards, self._s.revision_session_max_cards)
        ids = await self._repo.select_for_session(
            user.id,
            day_end=end,
            subject_id=subject_id,
            chapter_id=chapter_id,
            limit=size,
            new_limit=new_room,
        )
        if not ids:
            raise NothingDueError
        session = RevisionSession(
            user_id=user.id,
            subject_id=subject_id,
            chapter_id=chapter_id,
            status="active",
            started_at=now,
            last_activity_at=now,
            total_cards=len(ids),
            reviewed_cards=0,
            card_ids=[str(i) for i in ids],
        )
        try:
            await self._repo.add_session(session)
            await self._db.commit()
        except IntegrityError:  # a concurrent start won the one-active-session index
            await self._db.rollback()
            winner = await self._repo.active_session(user.id)
            if winner is None:
                raise
            return winner, True
        return session, False

    async def _session(
        self, user: User, session_id: uuid.UUID, *, lock: bool = False
    ) -> RevisionSession:
        session = await self._repo.get_session(session_id, user.id, lock=lock)
        if session is None:
            raise SessionNotFoundError
        return session

    async def _close_if_stale(self, session: RevisionSession) -> None:
        if session.status != "active":
            return
        idle = timedelta(minutes=self._s.revision_session_idle_minutes)
        if _now() - session.last_activity_at > idle:
            session.status = "abandoned"
            await self._db.commit()

    async def get_session(
        self, user: User, session_id: uuid.UUID
    ) -> tuple[RevisionSession, list[tuple[Row, bool]], dict[str, Any] | None]:
        session = await self._session(user, session_id)
        await self._close_if_stale(session)
        ids = [uuid.UUID(i) for i in session.card_ids]
        cards = await self._repo.cards_by_ids(user.id, ids)
        reviews = await self._repo.session_review_summary(session.id, user.id)
        reviewed_ids = {r[0] for r in reviews}
        items = [(cards[i], i in reviewed_ids) for i in ids if i in cards]  # deleted cards skipped
        summary = None
        if session.status != "active":
            summary = await self._summary(user, session, reviews)
        return session, items, summary

    async def list_sessions(
        self, user: User, status: str | None, limit: int, offset: int
    ) -> tuple[list[RevisionSession], int]:
        rows, total = await self._repo.list_sessions(user.id, status, limit, offset)
        for row in rows:
            await self._close_if_stale(row)
        return rows, total

    async def _summary(
        self,
        user: User,
        session: RevisionSession,
        reviews: list[tuple[uuid.UUID, str, datetime, int | None]],
    ) -> dict[str, Any]:
        dist = Counter(r[1] for r in reviews)
        times = [r[3] for r in reviews if r[3] is not None]
        ids = [uuid.UUID(i) for i in session.card_ids]
        return {
            "reviewed_cards": session.reviewed_cards,
            "total_cards": session.total_cards,
            "rating_distribution": {r: dist.get(r, 0) for r in ("again", "hard", "good", "easy")},
            "duration_seconds": session.duration_seconds,
            "average_response_ms": round(sum(times) / len(times)) if times else None,
            "next_due_at": await self._repo.next_due(user.id, ids),
        }

    async def complete_session(self, user: User, session_id: uuid.UUID) -> RevisionSession:
        session = await self._session(user, session_id, lock=True)
        if session.status == "completed":
            await self._db.commit()
            return session
        if session.status != "active":
            await self._db.rollback()
            raise SessionNotActiveError
        now = _now()
        idle = timedelta(minutes=self._s.revision_session_idle_minutes)
        end = min(now, session.last_activity_at + idle)  # do not count idle time as study time
        session.status = "completed"
        session.completed_at = now
        session.duration_seconds = max(0, int((end - session.started_at).total_seconds()))
        await self._db.commit()
        return session

    async def abandon_session(self, user: User, session_id: uuid.UUID) -> RevisionSession:
        session = await self._session(user, session_id, lock=True)
        if session.status == "completed":
            await self._db.rollback()
            raise SessionNotActiveError
        if session.status == "active":
            session.status = "abandoned"
        await self._db.commit()
        return session


def material_of(row: Row) -> StudyMaterial:
    return row[2]


def card_of(row: Row) -> Flashcard:
    return row[0]
