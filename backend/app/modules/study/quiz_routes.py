"""Quiz routes (spec 19.4). All need an active session; ownership is checked in the service and a
foreign id is a 404. No route before submission returns an answer key (D-94)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response

from app.core.dependencies import ActiveUser, DbSession
from app.models.quiz import QuizAttempt, QuizQuestion
from app.modules.study.quiz_schemas import (
    AttemptListOut,
    AttemptListResponse,
    AttemptOut,
    AttemptResponse,
    AttemptSummary,
    OptionOut,
    QuizOut,
    QuizQuestionOut,
    QuizResponse,
    ResultOut,
    ResultQuestionOut,
    ResultResponse,
    SaveAnswersRequest,
    SubmitRequest,
)
from app.modules.study.quiz_service import RESULT_NOTE, QuizService, _now
from app.study.quiz_grading import OBJECTIVE_TYPES, answer_format

router = APIRouter(prefix="/study/quizzes", tags=["study-quizzes"])


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


def _attempt(attempt: QuizAttempt, questions: list[QuizQuestion]) -> AttemptOut:
    now = _now()
    remaining = None
    if attempt.expires_at is not None and attempt.status == "in_progress":
        remaining = max(0, int((attempt.expires_at - now).total_seconds()))
    submitted = attempt.status == "submitted"
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
        questions=[] if submitted else [_question(q) for q in questions],
        score=float(attempt.score) if attempt.score is not None else None,
        total_questions=attempt.total_questions,
        graded_questions=attempt.graded_questions,
        percentage=float(attempt.percentage) if attempt.percentage is not None else None,
    )


async def _attempt_out(service: QuizService, user: ActiveUser, attempt: QuizAttempt) -> AttemptOut:
    questions = (
        [] if attempt.status == "submitted" else await service.questions_in_order(user, attempt)
    )
    return _attempt(attempt, questions)


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
            items=[
                AttemptSummary(
                    id=a.id,
                    status=a.status,  # type: ignore[arg-type]
                    started_at=a.started_at,
                    submitted_at=a.submitted_at,
                    auto_submitted=a.auto_submitted,
                    score=float(a.score) if a.score is not None else None,
                    total_questions=a.total_questions,
                    graded_questions=a.graded_questions,
                    percentage=float(a.percentage) if a.percentage is not None else None,
                )
                for a in rows
            ],
            total=total,
            limit=limit,
            offset=offset,
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
) -> AttemptResponse:
    service = QuizService(db)
    attempt = await service.submit(
        current_user, quiz_id, attempt_id, [(a.question_id, a.answer) for a in body.answers]
    )
    return AttemptResponse(data=await _attempt_out(service, current_user, attempt))


@router.get("/{quiz_id}/results/{attempt_id}", response_model=ResultResponse)
async def get_results(
    quiz_id: uuid.UUID, attempt_id: uuid.UUID, current_user: ActiveUser, db: DbSession
) -> ResultResponse:
    """The only route that returns correct answers and explanations: 409 until submitted."""
    attempt, questions, answers = await QuizService(db).results(current_user, quiz_id, attempt_id)
    items: list[ResultQuestionOut] = []
    correct = incorrect = unanswered = not_graded = 0
    for q in questions:
        row = answers.get(q.id)
        given = row.submitted_answer if row is not None else None
        answered = bool(given)
        objective = q.question_type in OBJECTIVE_TYPES
        is_correct = row.is_correct if row is not None else None
        if not answered:
            unanswered += 1
        elif not objective:
            not_graded += 1
        elif is_correct:
            correct += 1
        else:
            incorrect += 1
        items.append(
            ResultQuestionOut(
                id=q.id,
                question=q.question,
                question_type=q.question_type,  # type: ignore[arg-type]
                difficulty=q.difficulty,  # type: ignore[arg-type]
                options=[OptionOut(id=o["id"], text=o["text"]) for o in q.options],
                submitted_answer=given,
                answered=answered,
                grading="auto" if objective else "self_assessment",
                is_correct=is_correct,
                awarded_score=float(row.awarded_score) if row is not None else 0.0,
                correct_answers=list(q.correct_answers),
                rubric=list(q.rubric),
                explanation=q.explanation,
                source_references=list(q.source_references),
            )
        )
    assert attempt.submitted_at is not None
    return ResultResponse(
        data=ResultOut(
            attempt_id=attempt.id,
            quiz_id=attempt.quiz_id,
            total_questions=attempt.total_questions or 0,
            graded_questions=attempt.graded_questions or 0,
            correct=correct,
            incorrect=incorrect,
            unanswered=unanswered,
            not_graded=not_graded,
            score=float(attempt.score or 0),
            percentage=float(attempt.percentage) if attempt.percentage is not None else None,
            time_taken_seconds=max(
                0, int((attempt.submitted_at - attempt.started_at).total_seconds())
            ),
            auto_submitted=attempt.auto_submitted,
            started_at=attempt.started_at,
            submitted_at=attempt.submitted_at,
            note=RESULT_NOTE,
            questions=items,
        )
    )
