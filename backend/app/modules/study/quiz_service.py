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

from app.ai.orchestration.runtime import AiRuntime
from app.models.quiz import Quiz, QuizAttempt, QuizAttemptAnswer, QuizQuestion
from app.models.study_material import StudyMaterial
from app.models.user import User
from app.repositories.quiz_repository import QuizRepository
from app.study.errors import (
    CompareNotPossibleError,
    EvaluationUnavailableError,
    IdempotencyKeyReusedError,
    NothingToEvaluateError,
    QuizAnswerInvalidError,
    QuizAttemptAbandonedError,
    QuizAttemptExpiredError,
    QuizAttemptLimitError,
    QuizAttemptNotFoundError,
    QuizAttemptNotSubmittedError,
    QuizAttemptSubmittedError,
    QuizNotFoundError,
    StudyError,
)
from app.study.quiz_evaluation import QuizEvaluator
from app.study.quiz_grading import OBJECTIVE_TYPES, grade_question, validate_answer
from app.study.quiz_scoring import Totals, money, summarise

MAX_ATTEMPTS_PER_QUIZ = 100
# Extra seconds after the deadline in which the answers sent WITH a submit are still accepted
# (network delay of an auto-submit from the browser). Saving answers gets no grace.
SUBMIT_GRACE_SECONDS = 10
RESULT_NOTE = (
    "This score reflects only this quiz. It is not a measure of your overall mastery of the "
    "subject. Written answers are not graded automatically: compare them with the model answer "
    "and rubric."
)
RESULT_NOTE_AI = (
    "This score reflects only this quiz. It is not a measure of your overall mastery of the "
    "subject. Marks for written answers are an AI-assisted estimate against the stored model "
    "answer and rubric: treat them as indicative, not as an official grade."
)


def _now() -> datetime:
    return datetime.now(UTC)


class QuizService:
    def __init__(self, db: AsyncSession, runtime: AiRuntime | None = None) -> None:
        self._db = db
        self._quizzes = QuizRepository(db)
        self._runtime = runtime
        self._evaluator = QuizEvaluator(db, runtime) if runtime is not None else None

    @property
    def ai_grading(self) -> bool:
        """Written answers are graded by the AI layer when it is configured and enabled (D-112);
        otherwise they stay self-assessed exactly as in Phase 4 (D-96)."""
        return self._evaluator is not None and self._evaluator.available

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
        if attempt.status == "abandoned":
            await self._db.rollback()
            raise QuizAttemptAbandonedError
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
        idempotency_key: str | None = None,
    ) -> QuizAttempt:
        """Idempotent: an already submitted attempt is returned unchanged (answers in the body
        are ignored), so a retry after a lost response returns the same result. An optional
        idempotency key is stored with the attempt and is unique per user (D-109)."""
        quiz = await self._quiz(user, quiz_id)
        attempt = await self._owned_attempt(user, quiz, attempt_id, lock=True)
        if attempt.status == "submitted":
            await self._db.commit()  # nothing changed: releases the row lock
            return attempt
        if attempt.status == "abandoned":
            await self._db.rollback()
            raise QuizAttemptAbandonedError
        now = _now()
        late = self._expired(attempt, now, SUBMIT_GRACE_SECONDS)
        if not late:
            try:
                await self._merge(user, attempt, items)
            except QuizAnswerInvalidError:
                await self._db.rollback()
                raise
        if idempotency_key:
            attempt.submit_idempotency_key = idempotency_key
        try:
            await self._finalize(
                user, quiz, attempt, auto=self._expired(attempt, now), now=now, cap_at_deadline=True
            )
            await self._db.commit()
        except IntegrityError:  # the key belongs to another attempt of this user
            await self._db.rollback()
            raise IdempotencyKeyReusedError from None
        await self._evaluate(user, attempt, strict=False)
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
        ai = self.ai_grading
        rows: list[dict[str, Any]] = []
        for q in questions:
            answer = attempt.answers.get(str(q.id))
            result = grade_question(q, answer)
            row: dict[str, Any] = {
                "question_id": q.id,
                "submitted_answer": answer if result.answered else None,
                "feedback": None,
                "submitted_at": stamp,
            }
            if q.question_type in OBJECTIVE_TYPES:
                row.update(
                    is_correct=result.is_correct,
                    awarded_score=Decimal(str(result.awarded)),
                    max_score=Decimal(1),
                    grading_method="auto",
                    evaluation_status="graded",
                    ai_assisted=False,
                )
            elif not ai:  # Phase 4 behaviour: compare with the model answer yourself (D-96)
                row.update(
                    is_correct=None,
                    awarded_score=Decimal(0),
                    max_score=Decimal(0),
                    grading_method="self_assessment",
                    evaluation_status="not_graded",
                    ai_assisted=False,
                )
            elif result.answered:  # waits for AI grading: never a silent 0 (D-112)
                row.update(
                    is_correct=None,
                    awarded_score=Decimal(0),
                    max_score=Decimal(1),
                    grading_method="ai",
                    evaluation_status="pending",
                    ai_assisted=True,
                )
            else:  # nothing written: deterministically 0 of 1
                row.update(
                    is_correct=False,
                    awarded_score=Decimal(0),
                    max_score=Decimal(1),
                    grading_method="auto",
                    evaluation_status="graded",
                    ai_assisted=False,
                )
            rows.append(row)
        await self._quizzes.add_answer_rows(user.id, attempt.id, rows)
        attempt.status = "submitted"
        attempt.submitted_at = stamp
        attempt.auto_submitted = auto
        attempt.time_taken_seconds = max(0, int((stamp - attempt.started_at).total_seconds()))
        totals = summarise(questions, await self._quizzes.answer_rows(attempt.id, user.id))
        self._apply_totals(attempt, totals)

    @staticmethod
    def _apply_totals(attempt: QuizAttempt, t: Totals) -> None:
        attempt.score = money(t.score)
        attempt.max_score = money(t.max_score)
        attempt.total_questions = t.total_questions
        attempt.graded_questions = t.graded_questions
        attempt.percentage = money(t.score / t.max_score * 100) if t.max_score else None
        attempt.correct_answers = t.correct
        attempt.incorrect_answers = t.incorrect
        attempt.unanswered = t.unanswered
        attempt.evaluation_status = t.evaluation_status

    # AI-assisted grading ─────────────────────────────────────────────────────

    async def _evaluate(self, user: User, attempt: QuizAttempt, *, strict: bool) -> None:
        """Grade waiting written answers. After a submit (`strict=False`) a limit problem is
        swallowed: the answers stay pending and the retry endpoint finishes them."""
        if self._evaluator is None or not self.ai_grading:
            return
        pending = await self._quizzes.pending_answer_ids(attempt.id, user.id)
        if not pending:
            return
        try:
            await self._evaluator.enforce_limits(user.id)
        except StudyError:
            await self._db.commit()
            if strict:
                raise
            return
        questions = {q.id: q for q in await self._quizzes.questions(attempt.quiz_id, user.id)}
        await self._db.commit()  # no transaction is open while the provider works
        await self._evaluator.evaluate(user.id, questions, pending)
        await self._refresh_totals(user, attempt)

    async def _refresh_totals(self, user: User, attempt: QuizAttempt) -> None:
        questions = await self._quizzes.questions(attempt.quiz_id, user.id)
        rows = await self._quizzes.answer_rows(attempt.id, user.id)
        self._apply_totals(attempt, summarise(questions, rows))
        await self._db.commit()

    async def retry_evaluation(
        self, user: User, quiz_id: uuid.UUID, attempt_id: uuid.UUID
    ) -> QuizAttempt:
        quiz = await self._quiz(user, quiz_id)
        attempt = await self._owned_attempt(user, quiz, attempt_id)
        if attempt.status != "submitted":
            raise QuizAttemptNotSubmittedError
        if not await self._quizzes.pending_answer_ids(attempt.id, user.id):
            raise NothingToEvaluateError
        if not self.ai_grading:
            raise EvaluationUnavailableError
        await self._evaluate(user, attempt, strict=True)
        return attempt

    # lifecycle: abandon and delete ───────────────────────────────────────────

    async def abandon(self, user: User, quiz_id: uuid.UUID, attempt_id: uuid.UUID) -> QuizAttempt:
        """Give up an in-progress attempt (no score). Idempotent; a submitted attempt cannot be
        abandoned."""
        quiz = await self._quiz(user, quiz_id)
        attempt = await self._owned_attempt(user, quiz, attempt_id, lock=True)
        if attempt.status == "submitted":
            await self._db.rollback()
            raise QuizAttemptSubmittedError
        if attempt.status == "in_progress":
            attempt.status = "abandoned"
            attempt.abandoned_at = _now()
        await self._db.commit()
        return attempt

    async def delete_attempt(self, user: User, quiz_id: uuid.UUID, attempt_id: uuid.UUID) -> None:
        """Delete one of the user's own attempts with its answers. Statistics are derived from
        attempts (D-108), so it disappears from analytics too (D-115)."""
        quiz = await self._quiz(user, quiz_id)
        attempt = await self._owned_attempt(user, quiz, attempt_id, lock=True)
        await self._quizzes.delete_attempt(attempt.id, user.id)
        await self._db.commit()

    # history and comparison ──────────────────────────────────────────────────

    async def history(
        self,
        user: User,
        *,
        quiz_id: uuid.UUID | None,
        subject_id: uuid.UUID | None,
        chapter_id: uuid.UUID | None,
        status: str | None,
        date_from: datetime | None,
        date_to: datetime | None,
        limit: int,
        offset: int,
    ) -> tuple[list[tuple[QuizAttempt, Quiz, StudyMaterial]], int]:
        return await self._quizzes.attempts_filtered(
            user.id,
            quiz_id=quiz_id,
            subject_id=subject_id,
            chapter_id=chapter_id,
            status=status,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
            offset=offset,
        )

    async def compare(
        self, user: User, quiz_id: uuid.UUID, first_id: uuid.UUID, second_id: uuid.UUID
    ) -> dict[str, Any]:
        """Two submitted attempts of the same quiz, oldest first. Reports differences only: a
        higher score on one attempt does not prove retention (the UI says so)."""
        quiz = await self._quiz(user, quiz_id)
        if first_id == second_id:
            raise CompareNotPossibleError
        a = await self._owned_attempt(user, quiz, first_id)
        b = await self._owned_attempt(user, quiz, second_id)
        if a.status != "submitted" or b.status != "submitted":
            raise CompareNotPossibleError
        a, b = sorted((a, b), key=lambda x: (x.submitted_at or x.started_at, str(x.id)))
        questions = await self._quizzes.questions(quiz.id, user.id)
        rows_a = await self._quizzes.answer_rows(a.id, user.id)
        rows_b = await self._quizzes.answer_rows(b.id, user.id)
        ta, tb = summarise(questions, rows_a), summarise(questions, rows_b)
        by_a = {r.question_id: r for r in rows_a}
        by_b = {r.question_id: r for r in rows_b}
        changes: list[dict[str, Any]] = []
        for q in questions:
            ra, rb = by_a.get(q.id), by_b.get(q.id)
            if ra is None or rb is None:
                continue
            first, second = _share(ra), _share(rb)
            movement = "same"
            if first is not None and second is not None:
                movement = (
                    "improved" if second > first else "declined" if second < first else "same"
                )
            changes.append(
                {
                    "question_id": q.id,
                    "question": q.question,
                    "topic": q.topic,
                    "first": _label(ra),
                    "second": _label(rb),
                    "movement": movement,
                }
            )
        topics: list[dict[str, Any]] = []
        keys = sorted({*ta.topics, *tb.topics}, key=lambda t: (t is None, (t or "").casefold()))
        for key in keys:
            sa, sb = ta.topics.get(key), tb.topics.get(key)
            pa = sa.percentage if sa else None
            pb = sb.percentage if sb else None
            topics.append(
                {
                    "topic": key,
                    "first_percentage": pa,
                    "second_percentage": pb,
                    "change": round(pb - pa, 1) if pa is not None and pb is not None else None,
                }
            )
        return {
            "first": a,
            "second": b,
            "first_totals": ta,
            "second_totals": tb,
            "questions": changes,
            "topics": topics,
        }

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


def _share(row: QuizAttemptAnswer) -> float | None:
    """Fraction of the available marks awarded, or None while not graded."""
    if row.evaluation_status in ("pending", "failed", "not_graded"):
        return None
    available = float(row.max_score)
    return float(row.awarded_score) / available if available else None


def _label(row: QuizAttemptAnswer) -> str:
    if not row.submitted_answer:
        return "unanswered"
    if row.evaluation_status in ("pending", "failed"):
        return "pending"
    share = _share(row)
    if share is None:
        return "not_graded"
    return "correct" if share >= 0.999 else "incorrect" if share <= 0.001 else "partial"
