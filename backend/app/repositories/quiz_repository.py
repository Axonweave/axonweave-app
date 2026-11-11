"""Persistence for quizzes, questions and attempts. Every read and write is scoped by `user_id`."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.quiz import Quiz, QuizAttempt, QuizAttemptAnswer, QuizQuestion


class QuizRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create_quiz(
        self,
        *,
        user_id: uuid.UUID,
        material_id: uuid.UUID,
        title: str,
        description: str | None,
        time_limit: int | None,
        settings: dict[str, Any],
        questions: Sequence[dict[str, Any]],
    ) -> Quiz:
        quiz = Quiz(
            user_id=user_id,
            study_material_id=material_id,
            title=title,
            description=description,
            time_limit=time_limit,
            settings=settings,
        )
        self._db.add(quiz)
        await self._db.flush()
        self._db.add_all(
            QuizQuestion(user_id=user_id, quiz_id=quiz.id, display_order=i, **q)
            for i, q in enumerate(questions)
        )
        await self._db.flush()
        return quiz

    async def get_quiz(self, quiz_id: uuid.UUID, user_id: uuid.UUID) -> Quiz | None:
        return (
            await self._db.execute(select(Quiz).where(Quiz.id == quiz_id, Quiz.user_id == user_id))
        ).scalar_one_or_none()

    async def questions(self, quiz_id: uuid.UUID, user_id: uuid.UUID) -> list[QuizQuestion]:
        rows = await self._db.execute(
            select(QuizQuestion)
            .where(QuizQuestion.quiz_id == quiz_id, QuizQuestion.user_id == user_id)
            .order_by(QuizQuestion.display_order, QuizQuestion.id)
        )
        return list(rows.scalars())

    # attempts ────────────────────────────────────────────────────────────────

    async def add_attempt(
        self,
        *,
        user_id: uuid.UUID,
        quiz_id: uuid.UUID,
        question_order: list[str],
        started_at: datetime,
        expires_at: datetime | None,
    ) -> QuizAttempt:
        attempt = QuizAttempt(
            user_id=user_id,
            quiz_id=quiz_id,
            question_order=question_order,
            started_at=started_at,
            expires_at=expires_at,
        )
        self._db.add(attempt)
        await self._db.flush()
        return attempt

    async def get_attempt(
        self,
        attempt_id: uuid.UUID,
        quiz_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        lock: bool = False,
    ) -> QuizAttempt | None:
        stmt = select(QuizAttempt).where(
            QuizAttempt.id == attempt_id,
            QuizAttempt.quiz_id == quiz_id,
            QuizAttempt.user_id == user_id,
        )
        if lock:
            stmt = stmt.with_for_update()
        return (await self._db.execute(stmt)).scalar_one_or_none()

    async def open_attempt(
        self, quiz_id: uuid.UUID, user_id: uuid.UUID, *, lock: bool = False
    ) -> QuizAttempt | None:
        stmt = select(QuizAttempt).where(
            QuizAttempt.quiz_id == quiz_id,
            QuizAttempt.user_id == user_id,
            QuizAttempt.status == "in_progress",
        )
        if lock:
            stmt = stmt.with_for_update()
        return (await self._db.execute(stmt)).scalar_one_or_none()

    async def attempts(
        self, quiz_id: uuid.UUID, user_id: uuid.UUID, limit: int, offset: int
    ) -> tuple[list[QuizAttempt], int]:
        base = (QuizAttempt.quiz_id == quiz_id, QuizAttempt.user_id == user_id)
        total = int(
            (
                await self._db.execute(select(func.count()).select_from(QuizAttempt).where(*base))
            ).scalar_one()
        )
        rows = await self._db.execute(
            select(QuizAttempt)
            .where(*base)
            .order_by(QuizAttempt.started_at.desc(), QuizAttempt.id)
            .limit(limit)
            .offset(offset)
        )
        return list(rows.scalars()), total

    async def attempt_count(self, quiz_id: uuid.UUID, user_id: uuid.UUID) -> int:
        return int(
            (
                await self._db.execute(
                    select(func.count())
                    .select_from(QuizAttempt)
                    .where(QuizAttempt.quiz_id == quiz_id, QuizAttempt.user_id == user_id)
                )
            ).scalar_one()
        )

    async def add_answer_rows(
        self, user_id: uuid.UUID, attempt_id: uuid.UUID, rows: Sequence[dict[str, Any]]
    ) -> None:
        self._db.add_all(
            QuizAttemptAnswer(user_id=user_id, attempt_id=attempt_id, **r) for r in rows
        )
        await self._db.flush()

    async def answer_rows(
        self, attempt_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[QuizAttemptAnswer]:
        rows = await self._db.execute(
            select(QuizAttemptAnswer).where(
                QuizAttemptAnswer.attempt_id == attempt_id, QuizAttemptAnswer.user_id == user_id
            )
        )
        return list(rows.scalars())


def money(value: float) -> Decimal:
    return Decimal(str(round(value, 2)))
