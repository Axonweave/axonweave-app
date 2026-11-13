"""Quiz routes (spec 19.4; Phase 5 spec 5.1). All need an active session; ownership is checked in
the service and a foreign id is a 404. No route before submission returns an answer key (D-94).
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response

from app.ai.orchestration.runtime import Runtime
from app.core.dependencies import ActiveUser, DbSession
from app.models.quiz import QuizAttempt, QuizQuestion
from app.modules.study.quiz_schemas import (
    AttemptListOut,
    AttemptListResponse,
    AttemptOut,
    AttemptResponse,
    AttemptSummary,
    CompareOut,
    CompareQuestionOut,
    CompareResponse,
    CompareTopicOut,
    DeleteOut,
    DeleteResponse,
    EvaluationOut,
    HistoryItem,
    HistoryOut,
    HistoryResponse,
    OptionOut,
    QuizOut,
    QuizQuestionOut,
    QuizResponse,
    ResultOut,
    ResultQuestionOut,
    ResultResponse,
    SaveAnswersRequest,
    SubmitRequest,
    TopicResultOut,
)
from app.modules.study.quiz_service import RESULT_NOTE, RESULT_NOTE_AI, QuizService, _now
from app.study.quiz_grading import answer_format
from app.study.quiz_scoring import suggested_topics, summarise, topic_rows

router = APIRouter(prefix="/study/quizzes", tags=["study-quizzes"])
history_router = APIRouter(prefix="/study/quiz-attempts", tags=["study-quizzes"])

SUGGESTION_NOTE = (
    "These topics scored below 60% in this attempt and may need revision. One attempt is a small "
    "sample: it is a hint, not a verdict on what you know."
)
COMPARE_NOTE = (
    "A higher score on a later attempt does not prove you remember more: you may have seen the "
    "same questions before. Use it as one signal alongside spaced revision."
)


def _question(q: QuizQuestion) -> QuizQuestionOut:
    # Built field by field on purpose: the answer key columns are never touched here.
    return QuizQuestionOut(
        id=q.id,
        question=q.question,
        question_type=q.question_type,  # type: ignore[arg-type]
        difficulty=q.difficulty,  # type: ignore[arg-type]
        answer_format=answer_format(q.question_type),  # type: ignore[arg-type]
        options=[OptionOut(id=o["id"], text=o["text"]) for o in q.options],
        display_order=q.display_order,
    )


def _f(value: object) -> float | None:
    return float(value) if value is not None else None  # type: ignore[arg-type]


def _attempt(attempt: QuizAttempt, questions: list[QuizQuestion]) -> AttemptOut:
    now = _now()
    remaining = None
    if attempt.expires_at is not None and attempt.status == "in_progress":
        remaining = max(0, int((attempt.expires_at - now).total_seconds()))
    done = attempt.status != "in_progress"
    return AttemptOut(
        id=attempt.id,
        quiz_id=attempt.quiz_id,
        status=attempt.status,  # type: ignore[arg-type]
        started_at=attempt.started_at,
        expires_at=attempt.expires_at,
        server_time=now,
        seconds_remaining=remaining,
        submitted_at=attempt.submitted_at,
        auto_submitted=attempt.auto_submitted,
        question_order=[uuid.UUID(i) for i in attempt.question_order],
        answers=attempt.answers,
        flagged=[uuid.UUID(i) for i in attempt.flagged],
        questions=[] if done else [_question(q) for q in questions],
        score=_f(attempt.score),
        total_questions=attempt.total_questions,
        graded_questions=attempt.graded_questions,
        percentage=_f(attempt.percentage),
        evaluation_status=attempt.evaluation_status,  # type: ignore[arg-type]
        time_taken_seconds=attempt.time_taken_seconds,
    )


async def _attempt_out(service: QuizService, user: ActiveUser, attempt: QuizAttempt) -> AttemptOut:
    questions = (
        [] if attempt.status != "in_progress" else await service.questions_in_order(user, attempt)
    )
    return _attempt(attempt, questions)


def _summary(a: QuizAttempt) -> AttemptSummary:
    return AttemptSummary(
        id=a.id,
        status=a.status,  # type: ignore[arg-type]
        started_at=a.started_at,
        submitted_at=a.submitted_at,
        auto_submitted=a.auto_submitted,
        score=_f(a.score),
        total_questions=a.total_questions,
        graded_questions=a.graded_questions,
        percentage=_f(a.percentage),
        evaluation_status=a.evaluation_status,  # type: ignore[arg-type]
        time_taken_seconds=a.time_taken_seconds,
    )


@router.get("/{quiz_id}", response_model=QuizResponse)
async def get_quiz(quiz_id: uuid.UUID, current_user: ActiveUser, db: DbSession) -> QuizResponse:
    quiz, questions = await QuizService(db).get_quiz(current_user, quiz_id)
    return QuizResponse(
        data=QuizOut(
            id=quiz.id,
            study_material_id=quiz.study_material_id,
            title=quiz.title,
            description=quiz.description,
            time_limit_seconds=quiz.time_limit,
            randomize_order=bool(quiz.settings.get("randomize_order")),
            question_count=len(questions),
            questions=[_question(q) for q in questions],
            created_at=quiz.created_at,
        )
    )


@router.post("/{quiz_id}/attempts", response_model=AttemptResponse, status_code=201)
async def start_attempt(
    quiz_id: uuid.UUID, response: Response, current_user: ActiveUser, db: DbSession
) -> AttemptResponse:
    """Starts an attempt, or returns the open one (200) so a refresh resumes it."""
    service = QuizService(db)
    attempt, created = await service.start_attempt(current_user, quiz_id)
    if not created:
        response.status_code = 200
    return AttemptResponse(data=await _attempt_out(service, current_user, attempt))


@router.get("/{quiz_id}/attempts", response_model=AttemptListResponse)
async def list_attempts(
    quiz_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
) -> AttemptListResponse:
    rows, total = await QuizService(db).list_attempts(current_user, quiz_id, limit, offset)
    return AttemptListResponse(
        data=AttemptListOut(
            items=[_summary(a) for a in rows], total=total, limit=limit, offset=offset
        )
    )


@router.get("/{quiz_id}/attempts/compare", response_model=CompareResponse)
async def compare_attempts(
    quiz_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
    first: Annotated[uuid.UUID, Query()],
    second: Annotated[uuid.UUID, Query()],
) -> CompareResponse:
    """Two submitted attempts of this quiz, oldest first, with per-question and per-topic change."""
    data = await QuizService(db).compare(current_user, quiz_id, first, second)
    a, b = data["first"], data["second"]
    ta, tb = data["first_totals"], data["second_totals"]
    return CompareResponse(
        data=CompareOut(
            first=_summary(a),
            second=_summary(b),
            score_change=round(tb.score - ta.score, 2),
            percentage_change=(
                round(tb.percentage - ta.percentage, 2)
                if tb.percentage is not None and ta.percentage is not None
                else None
            ),
            time_change_seconds=(
                b.time_taken_seconds - a.time_taken_seconds
                if b.time_taken_seconds is not None and a.time_taken_seconds is not None
                else None
            ),
            questions=[CompareQuestionOut(**c) for c in data["questions"]],
            topics=[CompareTopicOut(**t) for t in data["topics"]],
            note=COMPARE_NOTE,
        )
    )


@router.get("/{quiz_id}/attempts/{attempt_id}", response_model=AttemptResponse)
async def get_attempt(
    quiz_id: uuid.UUID, attempt_id: uuid.UUID, current_user: ActiveUser, db: DbSession
) -> AttemptResponse:
    service = QuizService(db)
    attempt = await service.get_attempt(current_user, quiz_id, attempt_id)
    return AttemptResponse(data=await _attempt_out(service, current_user, attempt))


@router.put("/{quiz_id}/attempts/{attempt_id}/answers", response_model=AttemptResponse)
async def save_answers(
    quiz_id: uuid.UUID,
    attempt_id: uuid.UUID,
    body: SaveAnswersRequest,
    current_user: ActiveUser,
    db: DbSession,
) -> AttemptResponse:
    service = QuizService(db)
    attempt = await service.save_answers(
        current_user,
        quiz_id,
        attempt_id,
        [(a.question_id, a.answer) for a in body.answers],
        body.flagged,
    )
    return AttemptResponse(data=await _attempt_out(service, current_user, attempt))


@router.post("/{quiz_id}/attempts/{attempt_id}/submit", response_model=AttemptResponse)
async def submit_attempt(
    quiz_id: uuid.UUID,
    attempt_id: uuid.UUID,
    body: SubmitRequest,
    current_user: ActiveUser,
    db: DbSession,
    runtime: Runtime,
) -> AttemptResponse:
    """Idempotent: submitting again (or with the same idempotency key) returns the same result."""
    service = QuizService(db, runtime)
    attempt = await service.submit(
        current_user,
        quiz_id,
        attempt_id,
        [(a.question_id, a.answer) for a in body.answers],
        body.idempotency_key,
    )
    return AttemptResponse(data=await _attempt_out(service, current_user, attempt))


@router.post("/{quiz_id}/attempts/{attempt_id}/abandon", response_model=AttemptResponse)
async def abandon_attempt(
    quiz_id: uuid.UUID, attempt_id: uuid.UUID, current_user: ActiveUser, db: DbSession
) -> AttemptResponse:
    service = QuizService(db)
    attempt = await service.abandon(current_user, quiz_id, attempt_id)
    return AttemptResponse(data=await _attempt_out(service, current_user, attempt))


@router.post("/{quiz_id}/attempts/{attempt_id}/evaluation/retry", response_model=AttemptResponse)
async def retry_evaluation(
    quiz_id: uuid.UUID,
    attempt_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
    runtime: Runtime,
) -> AttemptResponse:
    """Grade the written answers that are still waiting (provider was down, output unusable)."""
    service = QuizService(db, runtime)
    attempt = await service.retry_evaluation(current_user, quiz_id, attempt_id)
    return AttemptResponse(data=await _attempt_out(service, current_user, attempt))


@router.delete("/{quiz_id}/attempts/{attempt_id}", response_model=DeleteResponse)
async def delete_attempt(
    quiz_id: uuid.UUID, attempt_id: uuid.UUID, current_user: ActiveUser, db: DbSession
) -> DeleteResponse:
    await QuizService(db).delete_attempt(current_user, quiz_id, attempt_id)
    return DeleteResponse(data=DeleteOut())


@router.get("/{quiz_id}/results/{attempt_id}", response_model=ResultResponse)
async def get_results(
    quiz_id: uuid.UUID, attempt_id: uuid.UUID, current_user: ActiveUser, db: DbSession
) -> ResultResponse:
    """The only route that returns correct answers and explanations: 409 until submitted."""
    attempt, questions, answers = await QuizService(db).results(current_user, quiz_id, attempt_id)
    totals = summarise(questions, list(answers.values()))
    items: list[ResultQuestionOut] = []
    for q in questions:
        row = answers.get(q.id)
        given = row.submitted_answer if row is not None else None
        detail = row.evaluation_detail if row is not None else None
        items.append(
            ResultQuestionOut(
                id=q.id,
                question=q.question,
                question_type=q.question_type,  # type: ignore[arg-type]
                difficulty=q.difficulty,  # type: ignore[arg-type]
                options=[OptionOut(id=o["id"], text=o["text"]) for o in q.options],
                submitted_answer=given,
                answered=bool(given),
                grading=row.grading_method if row is not None else "auto",  # type: ignore[arg-type]
                is_correct=row.is_correct if row is not None else None,
                awarded_score=float(row.awarded_score) if row is not None else 0.0,
                correct_answers=list(q.correct_answers),
                rubric=list(q.rubric),
                explanation=q.explanation,
                source_references=list(q.source_references),
                topic=q.topic,
                ai_assisted=bool(row.ai_assisted) if row is not None else False,
                evaluation_status=row.evaluation_status if row is not None else "graded",  # type: ignore[arg-type]
                evaluation=EvaluationOut(
                    explanation=str(detail.get("explanation", "")),
                    covered_points=[str(x) for x in detail.get("covered_points", [])],
                    missing_points=[str(x) for x in detail.get("missing_points", [])],
                )
                if detail
                else None,
            )
        )
    assert attempt.submitted_at is not None
    suggestions = suggested_topics(totals)
    return ResultResponse(
        data=ResultOut(
            attempt_id=attempt.id,
            quiz_id=attempt.quiz_id,
            total_questions=attempt.total_questions or 0,
            graded_questions=attempt.graded_questions or 0,
            correct=totals.correct,
            incorrect=totals.incorrect,
            unanswered=totals.unanswered,
            not_graded=totals.not_graded,
            score=float(attempt.score or 0),
            percentage=_f(attempt.percentage),
            time_taken_seconds=(
                attempt.time_taken_seconds
                if attempt.time_taken_seconds is not None
                else max(0, int((attempt.submitted_at - attempt.started_at).total_seconds()))
            ),
            auto_submitted=attempt.auto_submitted,
            started_at=attempt.started_at,
            submitted_at=attempt.submitted_at,
            note=RESULT_NOTE_AI if totals.ai_assisted else RESULT_NOTE,
            questions=items,
            max_score=totals.max_score,
            evaluation_status=totals.evaluation_status,  # type: ignore[arg-type]
            pending_evaluations=totals.pending + totals.failed,
            ai_assisted_questions=totals.ai_assisted,
            topic_performance=[TopicResultOut(**r) for r in topic_rows(totals)],
            suggested_topics=suggestions,
            suggested_topics_note=SUGGESTION_NOTE if suggestions else "",
        )
    )


@history_router.get("", response_model=HistoryResponse)
async def attempt_history(
    current_user: ActiveUser,
    db: DbSession,
    quiz_id: Annotated[uuid.UUID | None, Query()] = None,
    subject_id: Annotated[uuid.UUID | None, Query()] = None,
    chapter_id: Annotated[uuid.UUID | None, Query()] = None,
    status: Annotated[Literal["in_progress", "submitted", "abandoned"] | None, Query()] = None,
    date_from: Annotated[datetime | None, Query()] = None,
    date_to: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
) -> HistoryResponse:
    """Attempts across all the user's quizzes, newest first, with allow-listed filters."""
    if date_from is not None and date_from.tzinfo is None:
        date_from = date_from.replace(tzinfo=UTC)
    if date_to is not None and date_to.tzinfo is None:
        date_to = date_to.replace(tzinfo=UTC)
    if date_to is not None and date_from is not None and date_to < date_from:
        date_to = date_from
    rows, total = await QuizService(db).history(
        current_user,
        quiz_id=quiz_id,
        subject_id=subject_id,
        chapter_id=chapter_id,
        status=status,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return HistoryResponse(
        data=HistoryOut(
            items=[
                HistoryItem(
                    **_summary(a).model_dump(),
                    quiz_id=quiz.id,
                    quiz_title=quiz.title,
                    study_material_id=material.id,
                    subject_id=material.subject_id,
                    chapter_id=material.chapter_id,
                )
                for a, quiz, material in rows
            ],
            total=total,
            limit=limit,
            offset=offset,
        )
    )
