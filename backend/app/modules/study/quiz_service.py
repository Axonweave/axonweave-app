"""Quiz service (spec 7, 19.4, 21.4): read a quiz without its answer key, run attempts with a
server-side timer, grade objective questions on the server, and return results only after submit.

Rules (D-94): ownership first on every path (foreign or missing is a 404); the answer key is read
only to grade and to build the results of a submitted attempt; a submitted attempt never changes
and submitting again returns the same result; an expired attempt is submitted with the answers
that were saved before the deadline.
"""

from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.quiz import Quiz, QuizAttempt, QuizQuestion
from app.models.user import User
from app.repositories.quiz_repository import QuizRepository
from app.study.errors import (
    QuizAnswerInvalidError,
    QuizAttemptExpiredError,
    QuizAttemptLimitError,
    QuizAttemptNotFoundError,
    QuizAttemptNotSubmittedError,
    QuizAttemptSubmittedError,
    QuizNotFoundError,
)
from app.study.quiz_grading import OBJECTIVE_TYPES, grade_question, validate_answer

MAX_ATTEMPTS_PER_QUIZ = 100
# Extra seconds after the deadline in which the answers sent WITH a submit are still accepted
# (network delay of an auto-submit from the browser). Saving answers gets no grace.
SUBMIT_GRACE_SECONDS = 10
RESULT_NOTE = (
    "This score reflects only this quiz. It is not a measure of your overall mastery of the "
    "subject. Written answers are not graded automatically: compare them with the model answer "
    "and rubric."
)


def _now() -> datetime:
    return datetime.now(UTC)


class QuizService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._quizzes = QuizRepository(db)

    # reads ───────────────────────────────────────────────────────────────────

    async def _quiz(self, user: User, quiz_id: uuid.UUID) -> Quiz:
        quiz = await self._quizzes.get_quiz(quiz_id, user.id)
        if quiz is None:
            raise QuizNotFoundError
        return quiz

    async def get_quiz(self, user: User, quiz_id: uuid.UUID) -> tuple[Quiz, list[QuizQuestion]]:
        quiz = await self._quiz(user, quiz_id)
        return quiz, await self._quizzes.questions(quiz.id, user.id)

    async def questions_in_order(self, user: User, attempt: QuizAttempt) -> list[QuizQuestion]:
        rows = {str(q.id): q for q in await self._quizzes.questions(attempt.quiz_id, user.id)}
        return [rows[i] for i in attempt.question_order if i in rows]

    # attempts ────────────────────────────────────────────────────────────────

    def _expired(self, attempt: QuizAttempt, now: datetime, grace: int = 0) -> bool:
        return (
            attempt.status == "in_progress"
            and attempt.expires_at is not None
            and now > attempt.expires_at + timedelta(seconds=grace)
        )

    async def start_attempt(self, user: User, quiz_id: uuid.UUID) -> tuple[QuizAttempt, bool]:
        """A new attempt, or the open one (resume). Retakes are unlimited up to a cap; an open
        attempt must be submitted (or expire) before a new one starts."""
        quiz = await self._quiz(user, quiz_id)
        now = _now()
        open_attempt = await self._quizzes.open_attempt(quiz.id, user.id, lock=True)
        if open_attempt is not None:
            if not self._expired(open_attempt, now):
                return open_attempt, False
            await self._finalize(user, quiz, open_attempt, auto=True, now=now)
        if await self._quizzes.attempt_count(quiz.id, user.id) >= MAX_ATTEMPTS_PER_QUIZ:
            await self._db.commit()
            raise QuizAttemptLimitError
        questions = await self._quizzes.questions(quiz.id, user.id)
        order = [str(q.id) for q in questions]
        if quiz.settings.get("randomize_order"):
            random.SystemRandom().shuffle(order)
        try:
            attempt = await self._quizzes.add_attempt(
                user_id=user.id,
                quiz_id=quiz.id,
                question_order=order,
                started_at=now,
                expires_at=now + timedelta(seconds=quiz.time_limit) if quiz.time_limit else None,
            )
            await self._db.commit()
        except IntegrityError:  # a concurrent start won the one-open-attempt index
            await self._db.rollback()
            winner = await self._quizzes.open_attempt(quiz.id, user.id)
            if winner is None:
                raise
            return winner, False
        return attempt, True

    async def get_attempt(
        self, user: User, quiz_id: uuid.UUID, attempt_id: uuid.UUID
    ) -> QuizAttempt:
        quiz = await self._quiz(user, quiz_id)
        attempt = await self._owned_attempt(user, quiz, attempt_id, lock=True)
        now = _now()
        if self._expired(attempt, now):
            await self._finalize(user, quiz, attempt, auto=True, now=now)
            await self._db.commit()
        else:
            await self._db.commit()  # nothing changed: releases the row lock
        return attempt

    async def _owned_attempt(
        self, user: User, quiz: Quiz, attempt_id: uuid.UUID, *, lock: bool = False
    ) -> QuizAttempt:
        attempt = await self._quizzes.get_attempt(attempt_id, quiz.id, user.id, lock=lock)
        if attempt is None:
            raise QuizAttemptNotFoundError
        return attempt

    async def list_attempts(
        self, user: User, quiz_id: uuid.UUID, limit: int, offset: int
    ) -> tuple[list[QuizAttempt], int]:
        quiz = await self._quiz(user, quiz_id)
        return await self._quizzes.attempts(quiz.id, user.id, limit, offset)

    # answers ─────────────────────────────────────────────────────────────────

    async def _merge(
        self,
        user: User,
        attempt: QuizAttempt,
        items: list[tuple[uuid.UUID, Any]],
    ) -> None:
        if not items:
            return
        questions = {q.id: q for q in await self._quizzes.questions(attempt.quiz_id, user.id)}
        merged = dict(attempt.answers)
        for question_id, raw in items:
            question = questions.get(question_id)
            if question is None:  # not a question of this quiz
                raise QuizAnswerInvalidError
            merged[str(question_id)] = validate_answer(question, raw)
        attempt.answers = merged

    async def save_answers(
        self,
        user: User,
        quiz_id: uuid.UUID,
        attempt_id: uuid.UUID,
        items: list[tuple[uuid.UUID, Any]],
        flagged: list[uuid.UUID] | None,
    ) -> QuizAttempt:
        quiz = await self._quiz(user, quiz_id)
        attempt = await self._owned_attempt(user, quiz, attempt_id, lock=True)
        if attempt.status == "submitted":
            await self._db.rollback()
            raise QuizAttemptSubmittedError
        now = _now()
        if self._expired(attempt, now):
            await self._finalize(user, quiz, attempt, auto=True, now=now)
            await self._db.commit()
            raise QuizAttemptExpiredError
        try:
            await self._merge(user, attempt, items)
        except QuizAnswerInvalidError:
            await self._db.rollback()
            raise
        if flagged is not None:
            known = {str(i) for i in attempt.question_order}
            attempt.flagged = [str(f) for f in dict.fromkeys(flagged) if str(f) in known]
        await self._db.commit()
        return attempt

    async def submit(
        self,
        user: User,
        quiz_id: uuid.UUID,
        attempt_id: uuid.UUID,
        items: list[tuple[uuid.UUID, Any]],
    ) -> QuizAttempt:
        """Idempotent: an already submitted attempt is returned unchanged (answers in the body
        are ignored)."""
        quiz = await self._quiz(user, quiz_id)
        attempt = await self._owned_attempt(user, quiz, attempt_id, lock=True)
        if attempt.status == "submitted":
            await self._db.commit()  # nothing changed: releases the row lock
            return attempt
        now = _now()
        late = self._expired(attempt, now, SUBMIT_GRACE_SECONDS)
        if not late:
            try:
                await self._merge(user, attempt, items)
            except QuizAnswerInvalidError:
                await self._db.rollback()
                raise
        await self._finalize(
            user, quiz, attempt, auto=self._expired(attempt, now), now=now, cap_at_deadline=True
        )
        await self._db.commit()
        return attempt

    async def _finalize(
        self,
        user: User,
        quiz: Quiz,
        attempt: QuizAttempt,
        *,
        auto: bool,
        now: datetime,
        cap_at_deadline: bool = False,
    ) -> None:
        """Grade and freeze. The caller holds the row lock and commits."""
        questions = await self._quizzes.questions(quiz.id, user.id)
        stamp = now
        if attempt.expires_at is not None and (auto or now > attempt.expires_at):
            stamp = attempt.expires_at  # time taken never exceeds the limit
        rows: list[dict[str, Any]] = []
        score = 0.0
        graded = 0
        for q in questions:
            answer = attempt.answers.get(str(q.id))
            result = grade_question(q, answer)
            if q.question_type in OBJECTIVE_TYPES:
                graded += 1
            score += result.awarded
            rows.append(
                {
                    "question_id": q.id,
                    "submitted_answer": answer if result.answered else None,
                    "is_correct": result.is_correct,
                    "awarded_score": Decimal(str(result.awarded)),
                    "feedback": None,
                    "submitted_at": stamp,
                }
            )
        await self._quizzes.add_answer_rows(user.id, attempt.id, rows)
        attempt.status = "submitted"
        attempt.submitted_at = stamp
        attempt.auto_submitted = auto
        attempt.score = Decimal(str(round(score, 2)))
        attempt.total_questions = len(questions)
        attempt.graded_questions = graded
        attempt.percentage = Decimal(str(round(score / graded * 100, 2))) if graded else None

    # results ─────────────────────────────────────────────────────────────────

    async def results(
        self, user: User, quiz_id: uuid.UUID, attempt_id: uuid.UUID
    ) -> tuple[QuizAttempt, list[QuizQuestion], dict[uuid.UUID, Any]]:
        """The only path that reads the answer key back out. Needs a SUBMITTED attempt."""
        attempt = await self.get_attempt(user, quiz_id, attempt_id)
        if attempt.status != "submitted":
            raise QuizAttemptNotSubmittedError
        questions = await self._quizzes.questions(attempt.quiz_id, user.id)
        answers = {a.question_id: a for a in await self._quizzes.answer_rows(attempt.id, user.id)}
        order = {i: n for n, i in enumerate(attempt.question_order)}
        questions.sort(key=lambda q: order.get(str(q.id), len(order)))
        return attempt, questions, answers
