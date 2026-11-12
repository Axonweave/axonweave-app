"""Read-only aggregate queries for learning analytics (Phase 5 M5; D-108, D-111).

Nothing is stored: every figure is derived from quiz attempts, answers, review events and revision
sessions. Every table in every join is filtered by `user_id`, so one user can never see another's
data. Dates are the user's LOCAL days: timestamps are converted with `timezone(<iana>, ts)::date`.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, and_, cast, func, select, union
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.flashcard import Flashcard, FlashcardSet
from app.models.quiz import Quiz, QuizAttempt, QuizAttemptAnswer, QuizQuestion
from app.models.revision import FlashcardReview, FlashcardScheduling, RevisionSession
from app.models.study_material import StudyMaterial
from app.models.subject import Subject
from app.models.workspace import Workspace

Window = tuple[datetime | None, datetime | None]


class AnalyticsRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # scoping helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _attempt_conds(
        user_id: uuid.UUID,
        subject_id: uuid.UUID | None,
        chapter_id: uuid.UUID | None,
        window: Window,
    ) -> list[Any]:
        conds: list[Any] = [
            QuizAttempt.user_id == user_id,
            Quiz.user_id == user_id,
            StudyMaterial.user_id == user_id,
            QuizAttempt.status == "submitted",
            QuizAttempt.submitted_at.is_not(None),
        ]
        if subject_id is not None:
            conds.append(StudyMaterial.subject_id == subject_id)
        if chapter_id is not None:
            conds.append(StudyMaterial.chapter_id == chapter_id)
        if window[0] is not None:
            conds.append(QuizAttempt.submitted_at >= window[0])
        if window[1] is not None:
            conds.append(QuizAttempt.submitted_at < window[1])
        return conds

    @staticmethod
    def _attempt_from(stmt: Any) -> Any:
        return (
            stmt.select_from(QuizAttempt)
            .join(Quiz, and_(Quiz.id == QuizAttempt.quiz_id, Quiz.user_id == QuizAttempt.user_id))
            .join(StudyMaterial, StudyMaterial.id == Quiz.study_material_id)
        )

    @staticmethod
    def _review_conds(
        user_id: uuid.UUID,
        subject_id: uuid.UUID | None,
        chapter_id: uuid.UUID | None,
        window: Window,
    ) -> list[Any]:
        conds: list[Any] = [
            FlashcardReview.user_id == user_id,
            Flashcard.user_id == user_id,
            FlashcardSet.user_id == user_id,
            StudyMaterial.user_id == user_id,
        ]
        if subject_id is not None:
            conds.append(StudyMaterial.subject_id == subject_id)
        if chapter_id is not None:
            conds.append(StudyMaterial.chapter_id == chapter_id)
        if window[0] is not None:
            conds.append(FlashcardReview.reviewed_at >= window[0])
        if window[1] is not None:
            conds.append(FlashcardReview.reviewed_at < window[1])
        return conds

    @staticmethod
    def _review_from(stmt: Any) -> Any:
        return (
            stmt.select_from(FlashcardReview)
            .join(
                Flashcard,
                and_(
                    Flashcard.id == FlashcardReview.flashcard_id,
                    Flashcard.user_id == FlashcardReview.user_id,
                ),
            )
            .join(FlashcardSet, FlashcardSet.id == Flashcard.flashcard_set_id)
            .join(StudyMaterial, StudyMaterial.id == FlashcardSet.study_material_id)
        )

    @staticmethod
    def _session_conds(
        user_id: uuid.UUID,
        subject_id: uuid.UUID | None,
        chapter_id: uuid.UUID | None,
        window: Window,
    ) -> list[Any]:
        conds: list[Any] = [
            RevisionSession.user_id == user_id,
            RevisionSession.status == "completed",
            RevisionSession.completed_at.is_not(None),
        ]
        if subject_id is not None:
            conds.append(RevisionSession.subject_id == subject_id)
        if chapter_id is not None:
            conds.append(RevisionSession.chapter_id == chapter_id)
        if window[0] is not None:
            conds.append(RevisionSession.completed_at >= window[0])
        if window[1] is not None:
            conds.append(RevisionSession.completed_at < window[1])
        return conds

    # quizzes ─────────────────────────────────────────────────────────────────

    async def quiz_totals(
        self,
        user_id: uuid.UUID,
        subject_id: uuid.UUID | None,
        chapter_id: uuid.UUID | None,
        window: Window,
    ) -> dict[str, Any]:
        stmt = self._attempt_from(
            select(
                func.count(QuizAttempt.id),
                func.count(func.distinct(QuizAttempt.quiz_id)),
                func.avg(QuizAttempt.percentage),
                func.coalesce(func.sum(QuizAttempt.time_taken_seconds), 0),
            )
        ).where(*self._attempt_conds(user_id, subject_id, chapter_id, window))
        row = (await self._db.execute(stmt)).one()
        return {
            "attempts": int(row[0]),
            "quizzes": int(row[1]),
            "average_percentage": round(float(row[2]), 1) if row[2] is not None else None,
            "time_seconds": int(row[3]),
        }

    async def quiz_points(
        self,
        user_id: uuid.UUID,
        subject_id: uuid.UUID | None,
        chapter_id: uuid.UUID | None,
        window: Window,
        limit: int,
    ) -> list[tuple[QuizAttempt, Quiz]]:
        """The newest `limit` submitted attempts in the window, returned oldest first."""
        stmt = (
            self._attempt_from(select(QuizAttempt, Quiz))
            .where(*self._attempt_conds(user_id, subject_id, chapter_id, window))
            .order_by(QuizAttempt.submitted_at.desc(), QuizAttempt.id)
            .limit(limit)
        )
        rows = [(r[0], r[1]) for r in (await self._db.execute(stmt)).all()]
        rows.reverse()
        return rows

    async def subject_quiz(
        self,
        user_id: uuid.UUID,
        subject_id: uuid.UUID | None,
        chapter_id: uuid.UUID | None,
        window: Window,
    ) -> dict[uuid.UUID | None, dict[str, Any]]:
        stmt = self._attempt_from(
            select(
                StudyMaterial.subject_id,
                func.count(QuizAttempt.id),
                func.avg(QuizAttempt.percentage),
                func.max(QuizAttempt.submitted_at),
            )
        ).where(*self._attempt_conds(user_id, subject_id, chapter_id, window))
        stmt = stmt.group_by(StudyMaterial.subject_id)
        return {
            r[0]: {
                "attempts": int(r[1]),
                "average_percentage": round(float(r[2]), 1) if r[2] is not None else None,
                "last_attempt_at": r[3],
            }
            for r in (await self._db.execute(stmt)).all()
        }

    async def topic_attempt_rows(
        self,
        user_id: uuid.UUID,
        subject_id: uuid.UUID | None,
        chapter_id: uuid.UUID | None,
        window: Window,
        max_attempts: int,
    ) -> list[dict[str, Any]]:
        """Per (attempt, topic) sums of graded answers, for the newest `max_attempts` attempts.
        Pending and not-graded answers are excluded: they are evidence of nothing yet."""
        recent = (
            self._attempt_from(select(QuizAttempt.id))
            .where(*self._attempt_conds(user_id, subject_id, chapter_id, window))
            .order_by(QuizAttempt.submitted_at.desc(), QuizAttempt.id)
            .limit(max_attempts)
            .subquery()
        )
        stmt = (
            select(
                QuizAttempt.id,
                QuizAttempt.submitted_at,
                QuizQuestion.topic,
                func.sum(QuizAttemptAnswer.awarded_score),
                func.sum(QuizAttemptAnswer.max_score),
                func.count(QuizAttemptAnswer.id),
                func.count().filter(QuizAttemptAnswer.is_correct.is_(True)),
            )
            .select_from(QuizAttemptAnswer)
            .join(
                QuizAttempt,
                and_(
                    QuizAttempt.id == QuizAttemptAnswer.attempt_id,
                    QuizAttempt.user_id == QuizAttemptAnswer.user_id,
                ),
            )
            .join(
                QuizQuestion,
                and_(
                    QuizQuestion.id == QuizAttemptAnswer.question_id,
                    QuizQuestion.user_id == QuizAttemptAnswer.user_id,
                ),
            )
            .where(
                QuizAttemptAnswer.user_id == user_id,
                QuizAttempt.user_id == user_id,
                QuizQuestion.user_id == user_id,
                QuizAttempt.id.in_(select(recent.c.id)),
                QuizAttemptAnswer.evaluation_status == "graded",
                QuizAttemptAnswer.max_score > 0,
                QuizQuestion.topic.is_not(None),
            )
            .group_by(QuizAttempt.id, QuizAttempt.submitted_at, QuizQuestion.topic)
        )
        return [
            {
                "attempt_id": r[0],
                "submitted_at": r[1],
                "topic": r[2],
                "awarded": float(r[3] or 0),
                "available": float(r[4] or 0),
                "answers": int(r[5]),
                "correct": int(r[6]),
            }
            for r in (await self._db.execute(stmt)).all()
        ]

    async def per_day_quiz(
        self,
        user_id: uuid.UUID,
        tz: str,
        subject_id: uuid.UUID | None,
        chapter_id: uuid.UUID | None,
        window: Window,
    ) -> dict[date, int]:
        day = cast(func.timezone(tz, QuizAttempt.submitted_at), Date)
        stmt = (
            self._attempt_from(select(day, func.count(QuizAttempt.id)))
            .where(*self._attempt_conds(user_id, subject_id, chapter_id, window))
            .group_by(day)
        )
        return {r[0]: int(r[1]) for r in (await self._db.execute(stmt)).all()}

    # reviews ─────────────────────────────────────────────────────────────────

    async def review_totals(
        self,
        user_id: uuid.UUID,
        subject_id: uuid.UUID | None,
        chapter_id: uuid.UUID | None,
        window: Window,
    ) -> dict[str, Any]:
        stmt = self._review_from(
            select(
                func.count(FlashcardReview.id),
                func.count(func.distinct(FlashcardReview.flashcard_id)),
                func.avg(FlashcardReview.response_time_ms),
            )
        ).where(*self._review_conds(user_id, subject_id, chapter_id, window))
        row = (await self._db.execute(stmt)).one()
        return {
            "reviews": int(row[0]),
            "cards": int(row[1]),
            "average_response_ms": round(float(row[2])) if row[2] is not None else None,
        }

    async def rating_counts(
        self,
        user_id: uuid.UUID,
        subject_id: uuid.UUID | None,
        chapter_id: uuid.UUID | None,
        window: Window,
    ) -> dict[str, int]:
        stmt = (
            self._review_from(select(FlashcardReview.rating, func.count(FlashcardReview.id)))
            .where(*self._review_conds(user_id, subject_id, chapter_id, window))
            .group_by(FlashcardReview.rating)
        )
        return {r[0]: int(r[1]) for r in (await self._db.execute(stmt)).all()}

    async def reviews_by_subject(
        self,
        user_id: uuid.UUID,
        subject_id: uuid.UUID | None,
        chapter_id: uuid.UUID | None,
        window: Window,
    ) -> dict[uuid.UUID | None, dict[str, int]]:
        stmt = (
            self._review_from(
                select(
                    StudyMaterial.subject_id,
                    FlashcardReview.rating,
                    func.count(FlashcardReview.id),
                )
            )
            .where(*self._review_conds(user_id, subject_id, chapter_id, window))
            .group_by(StudyMaterial.subject_id, FlashcardReview.rating)
        )
        out: dict[uuid.UUID | None, dict[str, int]] = {}
        for sid, rating, count in (await self._db.execute(stmt)).all():
            out.setdefault(sid, {})[rating] = int(count)
        return out

    async def per_day_reviews(
        self,
        user_id: uuid.UUID,
        tz: str,
        subject_id: uuid.UUID | None,
        chapter_id: uuid.UUID | None,
        window: Window,
    ) -> dict[date, dict[str, int]]:
        day = cast(func.timezone(tz, FlashcardReview.reviewed_at), Date)
        stmt = (
            self._review_from(select(day, FlashcardReview.rating, func.count(FlashcardReview.id)))
            .where(*self._review_conds(user_id, subject_id, chapter_id, window))
            .group_by(day, FlashcardReview.rating)
        )
        out: dict[date, dict[str, int]] = {}
        for d, rating, count in (await self._db.execute(stmt)).all():
            out.setdefault(d, {})[rating] = int(count)
        return out

    async def struggle_by_topic(
        self,
        user_id: uuid.UUID,
        window: Window,
    ) -> dict[str, dict[str, int]]:
        """Flashcard reviews per card topic: total and how many were Again or Hard."""
        stmt = (
            self._review_from(
                select(
                    Flashcard.topic,
                    func.count(FlashcardReview.id),
                    func.count().filter(FlashcardReview.rating.in_(("again", "hard"))),
                    func.count().filter(FlashcardReview.rating == "again"),
                )
            )
            .where(*self._review_conds(user_id, None, None, window), Flashcard.topic.is_not(None))
            .group_by(Flashcard.topic)
        )
        return {
            r[0]: {"reviews": int(r[1]), "hard_or_again": int(r[2]), "again": int(r[3])}
            for r in (await self._db.execute(stmt)).all()
        }

    async def overdue_by_topic(self, user_id: uuid.UUID, before: datetime) -> dict[str, int]:
        sch = FlashcardScheduling
        stmt = (
            select(Flashcard.topic, func.count(Flashcard.id))
            .select_from(Flashcard)
            .join(sch, and_(sch.flashcard_id == Flashcard.id, sch.user_id == Flashcard.user_id))
            .where(
                Flashcard.user_id == user_id,
                sch.user_id == user_id,
                sch.suspended.is_(False),
                sch.state.in_(("learning", "review", "relearning")),
                sch.due_at < before,
                Flashcard.topic.is_not(None),
            )
            .group_by(Flashcard.topic)
        )
        return {r[0]: int(r[1]) for r in (await self._db.execute(stmt)).all()}

    # sessions ────────────────────────────────────────────────────────────────

    async def session_totals(
        self,
        user_id: uuid.UUID,
        subject_id: uuid.UUID | None,
        chapter_id: uuid.UUID | None,
        window: Window,
    ) -> dict[str, int]:
        stmt = select(
            func.count(RevisionSession.id),
            func.coalesce(func.sum(RevisionSession.duration_seconds), 0),
        ).where(*self._session_conds(user_id, subject_id, chapter_id, window))
        row = (await self._db.execute(stmt)).one()
        return {"sessions": int(row[0]), "time_seconds": int(row[1])}

    async def per_day_sessions(
        self,
        user_id: uuid.UUID,
        tz: str,
        subject_id: uuid.UUID | None,
        chapter_id: uuid.UUID | None,
        window: Window,
    ) -> dict[date, int]:
        day = cast(func.timezone(tz, RevisionSession.completed_at), Date)
        stmt = (
            select(day, func.count(RevisionSession.id))
            .where(*self._session_conds(user_id, subject_id, chapter_id, window))
            .group_by(day)
        )
        return {r[0]: int(r[1]) for r in (await self._db.execute(stmt)).all()}

    # streaks and calendar detail ─────────────────────────────────────────────

    async def active_dates(self, user_id: uuid.UUID, tz: str) -> list[date]:
        """Local days with any study activity: a submitted quiz, a review or a completed session."""
        quiz_day = cast(func.timezone(tz, QuizAttempt.submitted_at), Date)
        review_day = cast(func.timezone(tz, FlashcardReview.reviewed_at), Date)
        session_day = cast(func.timezone(tz, RevisionSession.completed_at), Date)
        q = select(quiz_day.label("d")).where(
            QuizAttempt.user_id == user_id,
            QuizAttempt.status == "submitted",
            QuizAttempt.submitted_at.is_not(None),
        )
        r = select(review_day.label("d")).where(FlashcardReview.user_id == user_id)
        s = select(session_day.label("d")).where(
            RevisionSession.user_id == user_id,
            RevisionSession.status == "completed",
            RevisionSession.completed_at.is_not(None),
        )
        rows = await self._db.execute(select(union(q, r, s).subquery().c.d).order_by("d"))
        return [row[0] for row in rows.all()]

    async def day_quiz_attempts(
        self, user_id: uuid.UUID, start: datetime, end: datetime
    ) -> list[tuple[QuizAttempt, Quiz]]:
        stmt = (
            self._attempt_from(select(QuizAttempt, Quiz))
            .where(*self._attempt_conds(user_id, None, None, (start, end)))
            .order_by(QuizAttempt.submitted_at)
        )
        return [(r[0], r[1]) for r in (await self._db.execute(stmt)).all()]

    async def day_sessions(
        self, user_id: uuid.UUID, start: datetime, end: datetime
    ) -> list[RevisionSession]:
        stmt = (
            select(RevisionSession)
            .where(*self._session_conds(user_id, None, None, (start, end)))
            .order_by(RevisionSession.completed_at)
        )
        return list((await self._db.execute(stmt)).scalars())

    # names ───────────────────────────────────────────────────────────────────

    async def subject_names(self, user_id: uuid.UUID, ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
        if not ids:
            return {}
        rows = await self._db.execute(
            select(Subject.id, Subject.name)
            .join(Workspace, Workspace.id == Subject.workspace_id)
            .where(Workspace.user_id == user_id, Subject.id.in_(ids))
        )
        return {r[0]: r[1] for r in rows.all()}
