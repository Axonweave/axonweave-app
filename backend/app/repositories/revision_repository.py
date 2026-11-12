"""Persistence for flashcard scheduling, review events and revision sessions (Phase 5 M3).

Every query is scoped by `user_id`, and every joined table (flashcards, sets, materials) is scoped
by it too. No SQL outside this file for the revision feature.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, and_, cast, exists, func, literal, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.flashcard import Flashcard, FlashcardSet
from app.models.revision import FlashcardReview, FlashcardScheduling, RevisionSession
from app.models.study_material import StudyMaterial
from app.models.subject import Subject
from app.models.workspace import Workspace

NOT_NEW = ("learning", "review", "relearning")
Row = tuple[Flashcard, FlashcardScheduling, StudyMaterial]


class RevisionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # scheduling rows ─────────────────────────────────────────────────────────

    async def ensure_scheduling(self, user_id: uuid.UUID, version: str) -> int:
        """Create the missing scheduling rows for the user's cards (lazily, idempotent). A new
        card is due at its creation time. Returns how many rows were created."""
        missing = ~exists().where(
            FlashcardScheduling.user_id == Flashcard.user_id,
            FlashcardScheduling.flashcard_id == Flashcard.id,
        )
        stmt = (
            insert(FlashcardScheduling)
            .from_select(
                [
                    "id",
                    "user_id",
                    "flashcard_id",
                    "state",
                    "due_at",
                    "elapsed_days",
                    "scheduled_days",
                    "repetitions",
                    "lapses",
                    "suspended",
                    "scheduler_version",
                    "version",
                ],
                select(
                    func.gen_random_uuid(),
                    Flashcard.user_id,
                    Flashcard.id,
                    literal("new"),
                    Flashcard.created_at,
                    literal(0),
                    literal(0),
                    literal(0),
                    literal(0),
                    literal(False),
                    literal(version),
                    literal(1),
                ).where(Flashcard.user_id == user_id, missing),
            )
            .on_conflict_do_nothing(constraint="uq_flashcard_scheduling_user_card")
        )
        result = await self._db.execute(stmt)
        return int(getattr(result, "rowcount", 0) or 0)

    async def owned_card(self, card_id: uuid.UUID, user_id: uuid.UUID) -> Row | None:
        """The card with its scheduling row (created on demand) and material."""
        row = await self._card_row(card_id, user_id)
        return row

    async def _card_row(
        self, card_id: uuid.UUID, user_id: uuid.UUID, *, lock: bool = False
    ) -> Row | None:
        stmt = (
            select(Flashcard, FlashcardScheduling, StudyMaterial)
            .join(
                FlashcardScheduling,
                and_(
                    FlashcardScheduling.flashcard_id == Flashcard.id,
                    FlashcardScheduling.user_id == Flashcard.user_id,
                ),
            )
            .join(FlashcardSet, FlashcardSet.id == Flashcard.flashcard_set_id)
            .join(StudyMaterial, StudyMaterial.id == FlashcardSet.study_material_id)
            .where(
                Flashcard.id == card_id,
                Flashcard.user_id == user_id,
                FlashcardSet.user_id == user_id,
                StudyMaterial.user_id == user_id,
            )
        )
        if lock:
            stmt = stmt.with_for_update(of=FlashcardScheduling)
        row = (await self._db.execute(stmt)).first()
        return None if row is None else (row[0], row[1], row[2])

    async def locked_card(self, card_id: uuid.UUID, user_id: uuid.UUID) -> Row | None:
        return await self._card_row(card_id, user_id, lock=True)

    async def card_exists(self, card_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        return (
            await self._db.execute(
                select(Flashcard.id).where(Flashcard.id == card_id, Flashcard.user_id == user_id)
            )
        ).first() is not None

    # lists ───────────────────────────────────────────────────────────────────

    def _bucket(self, bucket: str, day_start: datetime, day_end: datetime) -> list[Any]:
        sch = FlashcardScheduling
        if bucket == "due":  # due by the end of the local day, overdue included
            return [sch.suspended.is_(False), sch.state.in_(NOT_NEW), sch.due_at < day_end]
        if bucket == "overdue":
            return [sch.suspended.is_(False), sch.state.in_(NOT_NEW), sch.due_at < day_start]
        if bucket == "new":
            return [sch.suspended.is_(False), sch.state == "new"]
        if bucket == "suspended":
            return [sch.suspended.is_(True)]
        return []

    def _scope(
        self, user_id: uuid.UUID, subject_id: uuid.UUID | None, chapter_id: uuid.UUID | None
    ) -> list[Any]:
        conds: list[Any] = [
            Flashcard.user_id == user_id,
            FlashcardSet.user_id == user_id,
            StudyMaterial.user_id == user_id,
            FlashcardScheduling.user_id == user_id,
        ]
        if subject_id is not None:
            conds.append(StudyMaterial.subject_id == subject_id)
        if chapter_id is not None:
            conds.append(StudyMaterial.chapter_id == chapter_id)
        return conds

    def _joined(self) -> Any:
        return (
            select(Flashcard, FlashcardScheduling, StudyMaterial)
            .join(
                FlashcardScheduling,
                and_(
                    FlashcardScheduling.flashcard_id == Flashcard.id,
                    FlashcardScheduling.user_id == Flashcard.user_id,
                ),
            )
            .join(FlashcardSet, FlashcardSet.id == Flashcard.flashcard_set_id)
            .join(StudyMaterial, StudyMaterial.id == FlashcardSet.study_material_id)
        )

    async def list_cards(
        self,
        user_id: uuid.UUID,
        *,
        bucket: str,
        day_start: datetime,
        day_end: datetime,
        subject_id: uuid.UUID | None,
        chapter_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Row], int]:
        conds = self._scope(user_id, subject_id, chapter_id) + self._bucket(
            bucket, day_start, day_end
        )
        total = int(
            (
                await self._db.execute(
                    select(func.count())
                    .select_from(Flashcard)
                    .join(
                        FlashcardScheduling,
                        and_(
                            FlashcardScheduling.flashcard_id == Flashcard.id,
                            FlashcardScheduling.user_id == Flashcard.user_id,
                        ),
                    )
                    .join(FlashcardSet, FlashcardSet.id == Flashcard.flashcard_set_id)
                    .join(StudyMaterial, StudyMaterial.id == FlashcardSet.study_material_id)
                    .where(*conds)
                )
            ).scalar_one()
        )
        order: list[Any] = (
            [Flashcard.created_at, Flashcard.display_order, Flashcard.id]
            if bucket == "new"
            else [FlashcardScheduling.due_at, Flashcard.id]
        )
        rows = (
            await self._db.execute(
                self._joined().where(*conds).order_by(*order).limit(limit).offset(offset)
            )
        ).all()
        return [(r[0], r[1], r[2]) for r in rows], total

    async def select_for_session(
        self,
        user_id: uuid.UUID,
        *,
        day_end: datetime,
        subject_id: uuid.UUID | None,
        chapter_id: uuid.UUID | None,
        limit: int,
        new_limit: int,
    ) -> list[uuid.UUID]:
        """Due cards first (most overdue first), then new cards up to `new_limit`."""
        base = self._scope(user_id, subject_id, chapter_id)
        sch = FlashcardScheduling
        due = (
            await self._db.execute(
                select(Flashcard.id)
                .select_from(Flashcard)
                .join(sch, and_(sch.flashcard_id == Flashcard.id, sch.user_id == Flashcard.user_id))
                .join(FlashcardSet, FlashcardSet.id == Flashcard.flashcard_set_id)
                .join(StudyMaterial, StudyMaterial.id == FlashcardSet.study_material_id)
                .where(
                    *base, sch.suspended.is_(False), sch.state.in_(NOT_NEW), sch.due_at < day_end
                )
                .order_by(sch.due_at, Flashcard.id)
                .limit(limit)
            )
        ).scalars()
        ids = list(due)
        room = min(limit - len(ids), new_limit)
        if room > 0:
            fresh = (
                await self._db.execute(
                    select(Flashcard.id)
                    .select_from(Flashcard)
                    .join(
                        sch,
                        and_(sch.flashcard_id == Flashcard.id, sch.user_id == Flashcard.user_id),
                    )
                    .join(FlashcardSet, FlashcardSet.id == Flashcard.flashcard_set_id)
                    .join(StudyMaterial, StudyMaterial.id == FlashcardSet.study_material_id)
                    .where(*base, sch.suspended.is_(False), sch.state == "new")
                    .order_by(Flashcard.created_at, Flashcard.display_order, Flashcard.id)
                    .limit(room)
                )
            ).scalars()
            ids.extend(fresh)
        return ids

    async def cards_by_ids(
        self, user_id: uuid.UUID, ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, Row]:
        if not ids:
            return {}
        rows = (
            await self._db.execute(
                self._joined().where(
                    Flashcard.user_id == user_id,
                    FlashcardSet.user_id == user_id,
                    StudyMaterial.user_id == user_id,
                    Flashcard.id.in_(list(ids)),
                )
            )
        ).all()
        return {r[0].id: (r[0], r[1], r[2]) for r in rows}

    # counts and summary ──────────────────────────────────────────────────────

    async def counts(
        self,
        user_id: uuid.UUID,
        *,
        day_start: datetime,
        day_end: datetime,
        subject_id: uuid.UUID | None,
        chapter_id: uuid.UUID | None,
    ) -> dict[str, int]:
        sch = FlashcardScheduling
        active = sch.suspended.is_(False)
        not_new = sch.state.in_(NOT_NEW)
        stmt = (
            select(
                func.count().label("total"),
                func.count().filter(active, not_new, sch.due_at < day_end).label("due"),
                func.count().filter(active, not_new, sch.due_at < day_start).label("overdue"),
                func.count().filter(active, sch.state == "new").label("new"),
                func.count()
                .filter(active, sch.state.in_(("learning", "relearning")))
                .label("learning"),
                func.count().filter(active, sch.state == "review").label("review"),
                func.count().filter(sch.suspended.is_(True)).label("suspended"),
            )
            .select_from(Flashcard)
            .join(sch, and_(sch.flashcard_id == Flashcard.id, sch.user_id == Flashcard.user_id))
            .join(FlashcardSet, FlashcardSet.id == Flashcard.flashcard_set_id)
            .join(StudyMaterial, StudyMaterial.id == FlashcardSet.study_material_id)
            .where(*self._scope(user_id, subject_id, chapter_id))
        )
        row = (await self._db.execute(stmt)).one()
        return {k: int(v) for k, v in row._mapping.items()}

    async def reviewed_between(
        self,
        user_id: uuid.UUID,
        start: datetime,
        end: datetime,
        *,
        subject_id: uuid.UUID | None = None,
        chapter_id: uuid.UUID | None = None,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(FlashcardReview)
            .join(
                Flashcard,
                and_(
                    Flashcard.id == FlashcardReview.flashcard_id,
                    Flashcard.user_id == FlashcardReview.user_id,
                ),
            )
            .join(FlashcardSet, FlashcardSet.id == Flashcard.flashcard_set_id)
            .join(StudyMaterial, StudyMaterial.id == FlashcardSet.study_material_id)
            .where(
                FlashcardReview.user_id == user_id,
                FlashcardReview.reviewed_at >= start,
                FlashcardReview.reviewed_at < end,
                StudyMaterial.user_id == user_id,
            )
        )
        if subject_id is not None:
            stmt = stmt.where(StudyMaterial.subject_id == subject_id)
        if chapter_id is not None:
            stmt = stmt.where(StudyMaterial.chapter_id == chapter_id)
        return int((await self._db.execute(stmt)).scalar_one())

    async def new_cards_started_between(
        self, user_id: uuid.UUID, start: datetime, end: datetime
    ) -> int:
        """Distinct cards whose first review happened in the window (the daily new-card cap)."""
        stmt = select(func.count(func.distinct(FlashcardReview.flashcard_id))).where(
            FlashcardReview.user_id == user_id,
            FlashcardReview.reviewed_at >= start,
            FlashcardReview.reviewed_at < end,
            FlashcardReview.previous_state["state"].astext == "new",
        )
        return int((await self._db.execute(stmt)).scalar_one())

    async def upcoming(
        self,
        user_id: uuid.UUID,
        tz_name: str,
        start: datetime,
        end: datetime,
        *,
        subject_id: uuid.UUID | None,
        chapter_id: uuid.UUID | None,
    ) -> dict[date, int]:
        """Cards due per LOCAL day in [start, end) (suspended and never-reviewed cards excluded)."""
        sch = FlashcardScheduling
        local_day = cast(func.timezone(tz_name, sch.due_at), Date)
        stmt = (
            select(local_day, func.count())
            .select_from(Flashcard)
            .join(sch, and_(sch.flashcard_id == Flashcard.id, sch.user_id == Flashcard.user_id))
            .join(FlashcardSet, FlashcardSet.id == Flashcard.flashcard_set_id)
            .join(StudyMaterial, StudyMaterial.id == FlashcardSet.study_material_id)
            .where(
                *self._scope(user_id, subject_id, chapter_id),
                sch.suspended.is_(False),
                sch.state.in_(NOT_NEW),
                sch.due_at >= start,
                sch.due_at < end,
            )
            .group_by(local_day)
            .order_by(local_day)
        )
        return {r[0]: int(r[1]) for r in (await self._db.execute(stmt)).all()}

    async def subject_breakdown(
        self, user_id: uuid.UUID, *, day_end: datetime
    ) -> list[dict[str, Any]]:
        sch = FlashcardScheduling
        active = sch.suspended.is_(False)
        stmt = (
            select(
                StudyMaterial.subject_id,
                func.count().label("total"),
                func.count()
                .filter(active, sch.state.in_(NOT_NEW), sch.due_at < day_end)
                .label("due"),
                func.count().filter(active, sch.state == "new").label("new"),
            )
            .select_from(Flashcard)
            .join(sch, and_(sch.flashcard_id == Flashcard.id, sch.user_id == Flashcard.user_id))
            .join(FlashcardSet, FlashcardSet.id == Flashcard.flashcard_set_id)
            .join(StudyMaterial, StudyMaterial.id == FlashcardSet.study_material_id)
            .where(*self._scope(user_id, None, None))
            .group_by(StudyMaterial.subject_id)
        )
        rows = (await self._db.execute(stmt)).all()
        ids = [r[0] for r in rows if r[0] is not None]
        names: dict[uuid.UUID, str] = {}
        if ids:
            named = await self._db.execute(
                select(Subject.id, Subject.name)
                .join(Workspace, Workspace.id == Subject.workspace_id)
                .where(Workspace.user_id == user_id, Subject.id.in_(ids))
            )
            names = {r[0]: r[1] for r in named.all()}
        out = [
            {
                "subject_id": r[0],
                "subject_name": names.get(r[0]) if r[0] is not None else None,
                "total": int(r[1]),
                "due": int(r[2]),
                "new": int(r[3]),
            }
            for r in rows
        ]
        out.sort(key=lambda d: (d["subject_name"] is None, str(d["subject_name"] or "").casefold()))
        return out

    # review events ───────────────────────────────────────────────────────────

    async def review_by_key(self, user_id: uuid.UUID, key: str) -> FlashcardReview | None:
        return (
            await self._db.execute(
                select(FlashcardReview).where(
                    FlashcardReview.user_id == user_id, FlashcardReview.idempotency_key == key
                )
            )
        ).scalar_one_or_none()

    async def add_review(self, review: FlashcardReview) -> FlashcardReview:
        self._db.add(review)
        await self._db.flush()
        return review

    async def reviews_for_card(
        self, card_id: uuid.UUID, user_id: uuid.UUID, limit: int, offset: int
    ) -> tuple[list[FlashcardReview], int]:
        base = (FlashcardReview.flashcard_id == card_id, FlashcardReview.user_id == user_id)
        total = int(
            (
                await self._db.execute(
                    select(func.count()).select_from(FlashcardReview).where(*base)
                )
            ).scalar_one()
        )
        rows = await self._db.execute(
            select(FlashcardReview)
            .where(*base)
            .order_by(FlashcardReview.reviewed_at.desc(), FlashcardReview.id)
            .limit(limit)
            .offset(offset)
        )
        return list(rows.scalars()), total

    async def recent_reviews(self, user_id: uuid.UUID, limit: int) -> list[FlashcardReview]:
        rows = await self._db.execute(
            select(FlashcardReview)
            .where(FlashcardReview.user_id == user_id)
            .order_by(FlashcardReview.reviewed_at.desc(), FlashcardReview.id)
            .limit(limit)
        )
        return list(rows.scalars())

    async def session_review_summary(
        self, session_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[tuple[uuid.UUID, str, datetime, int | None]]:
        rows = await self._db.execute(
            select(
                FlashcardReview.flashcard_id,
                FlashcardReview.rating,
                FlashcardReview.reviewed_at,
                FlashcardReview.response_time_ms,
            )
            .where(FlashcardReview.session_id == session_id, FlashcardReview.user_id == user_id)
            .order_by(FlashcardReview.reviewed_at)
        )
        return [(r[0], r[1], r[2], r[3]) for r in rows.all()]

    async def session_has_review(
        self, session_id: uuid.UUID, card_id: uuid.UUID, user_id: uuid.UUID
    ) -> bool:
        return (
            await self._db.execute(
                select(FlashcardReview.id)
                .where(
                    FlashcardReview.session_id == session_id,
                    FlashcardReview.flashcard_id == card_id,
                    FlashcardReview.user_id == user_id,
                )
                .limit(1)
            )
        ).first() is not None

    async def next_due(self, user_id: uuid.UUID, card_ids: Sequence[uuid.UUID]) -> datetime | None:
        if not card_ids:
            return None
        sch = FlashcardScheduling
        return (
            await self._db.execute(
                select(func.min(sch.due_at)).where(
                    sch.user_id == user_id,
                    sch.flashcard_id.in_(list(card_ids)),
                    sch.suspended.is_(False),
                )
            )
        ).scalar_one_or_none()

    # sessions ────────────────────────────────────────────────────────────────

    async def active_session(
        self, user_id: uuid.UUID, *, lock: bool = False
    ) -> RevisionSession | None:
        stmt = select(RevisionSession).where(
            RevisionSession.user_id == user_id, RevisionSession.status == "active"
        )
        if lock:
            stmt = stmt.with_for_update()
        return (await self._db.execute(stmt)).scalar_one_or_none()

    async def get_session(
        self, session_id: uuid.UUID, user_id: uuid.UUID, *, lock: bool = False
    ) -> RevisionSession | None:
        stmt = select(RevisionSession).where(
            RevisionSession.id == session_id, RevisionSession.user_id == user_id
        )
        if lock:
            stmt = stmt.with_for_update()
        return (await self._db.execute(stmt)).scalar_one_or_none()

    async def add_session(self, session: RevisionSession) -> RevisionSession:
        self._db.add(session)
        await self._db.flush()
        return session

    async def list_sessions(
        self, user_id: uuid.UUID, status: str | None, limit: int, offset: int
    ) -> tuple[list[RevisionSession], int]:
        base = [RevisionSession.user_id == user_id]
        if status is not None:
            base.append(RevisionSession.status == status)
        total = int(
            (
                await self._db.execute(
                    select(func.count()).select_from(RevisionSession).where(*base)
                )
            ).scalar_one()
        )
        rows = await self._db.execute(
            select(RevisionSession)
            .where(*base)
            .order_by(RevisionSession.started_at.desc(), RevisionSession.id)
            .limit(limit)
            .offset(offset)
        )
        return list(rows.scalars()), total

    async def bump_session(
        self, session_id: uuid.UUID, user_id: uuid.UUID, now: datetime, *, reviewed: int
    ) -> None:
        await self._db.execute(
            update(RevisionSession)
            .where(RevisionSession.id == session_id, RevisionSession.user_id == user_id)
            .values(
                reviewed_cards=func.least(
                    RevisionSession.reviewed_cards + reviewed, RevisionSession.total_cards
                ),
                last_activity_at=now,
            )
        )
