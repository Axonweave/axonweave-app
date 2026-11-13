"""Misconception routes (Milestone 6.7). Scoped to the signed-in user; ids that are not theirs are a
404. Writes are covered by the app's CSRF protection (D-04). Detection calls a model only when the
safeguards in `app.knowledge.misconceptions` are met, and counts toward the daily token quota."""

import uuid
from typing import Literal

from fastapi import APIRouter, Query

from app.ai.orchestration.runtime import Runtime
from app.core.dependencies import ActiveUser, DbSession
from app.core.rate_limit import get_rate_limiter
from app.knowledge.misconception_review import MisconceptionReview
from app.knowledge.misconceptions import MisconceptionService
from app.models.learner import LearnerMisconception
from app.modules.knowledge.misconception_schemas import (
    DetectOut,
    DetectRequest,
    DetectResponse,
    MisconceptionEvidenceOut,
    MisconceptionEvidenceResponse,
    MisconceptionListResponse,
    MisconceptionOut,
    MisconceptionPatch,
    MisconceptionResponse,
    RelatedConceptOut,
)
from app.repositories.learner_misconception_repository import LearnerMisconceptionRepository

router = APIRouter(prefix="/knowledge/learner/misconceptions", tags=["knowledge-learner"])

TENTATIVE_BELOW = 0.7


async def _out(
    db: DbSession, user_id: uuid.UUID, rows: list[tuple[LearnerMisconception, str]]
) -> list[MisconceptionOut]:
    wanted = {uuid.UUID(i) for m, _ in rows for i in m.related_node_ids}
    names = await LearnerMisconceptionRepository(db).node_names(user_id, list(wanted))
    out: list[MisconceptionOut] = []
    for m, node_name in rows:
        related = [
            RelatedConceptOut(id=uuid.UUID(i), name=names[uuid.UUID(i)])
            for i in m.related_node_ids
            if uuid.UUID(i) in names
        ]
        out.append(
            MisconceptionOut(
                id=m.id,
                workspace_id=m.workspace_id,
                knowledge_node_id=m.knowledge_node_id,
                node_name=node_name,
                description=m.description,
                explanation=m.explanation,
                recommended_action=m.recommended_action,
                confidence=float(m.confidence),
                tentative=float(m.confidence) < TENTATIVE_BELOW,
                status=m.status,
                evidence_count=m.evidence_count,
                detection_version=m.detection_version,
                prompt_version=m.prompt_version,
                related_concepts=related,
                edited_by_user=m.edited_by_user,
                created_at=m.created_at,
                updated_at=m.updated_at,
                dismissed_at=m.dismissed_at,
            )
        )
    return out


async def _one(db: DbSession, user_id: uuid.UUID, m: LearnerMisconception) -> MisconceptionOut:
    names = await LearnerMisconceptionRepository(db).node_names(user_id, [m.knowledge_node_id])
    return (await _out(db, user_id, [(m, names.get(m.knowledge_node_id, ""))]))[0]


@router.post("/detect", response_model=DetectResponse)
async def detect(
    body: DetectRequest, current_user: ActiveUser, db: DbSession, runtime: Runtime
) -> DetectResponse:
    """Look for a recurring misunderstanding on one concept. Calls no model unless there are
    enough wrong answers across enough different questions."""
    result = await MisconceptionService(db, runtime, get_rate_limiter()).detect(
        current_user.id, body.node_id
    )
    names = await LearnerMisconceptionRepository(db).node_names(current_user.id, [body.node_id])
    name = names.get(body.node_id, "")
    return DetectResponse(
        data=DetectOut(
            outcome=result.outcome,
            wrong_answers=result.wrong_answers,
            questions=result.questions,
            misconceptions=await _out(db, current_user.id, [(m, name) for m in result.items]),
        )
    )


@router.get("", response_model=MisconceptionListResponse)
async def list_misconceptions(
    current_user: ActiveUser,
    db: DbSession,
    node_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
    status: Literal["suggested", "confirmed", "dismissed", "corrected"] | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> MisconceptionListResponse:
    rows, total = await LearnerMisconceptionRepository(db).list_for_user(
        current_user.id,
        node_id=node_id,
        workspace_id=workspace_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    return MisconceptionListResponse(
        data=await _out(db, current_user.id, rows), total=total, limit=limit, offset=offset
    )


@router.get("/{misconception_id}", response_model=MisconceptionResponse)
async def get_misconception(
    misconception_id: uuid.UUID, current_user: ActiveUser, db: DbSession
) -> MisconceptionResponse:
    row = await MisconceptionReview(db).get(current_user.id, misconception_id)
    return MisconceptionResponse(data=await _one(db, current_user.id, row))


@router.get("/{misconception_id}/evidence", response_model=MisconceptionEvidenceResponse)
async def misconception_evidence(
    misconception_id: uuid.UUID, current_user: ActiveUser, db: DbSession
) -> MisconceptionEvidenceResponse:
    """The wrong answers it rests on, read from the learner's own quiz data."""
    await MisconceptionReview(db).get(current_user.id, misconception_id)
    rows = await LearnerMisconceptionRepository(db).evidence_details(
        current_user.id, misconception_id
    )
    return MisconceptionEvidenceResponse(
        data=[
            MisconceptionEvidenceOut(
                answer_id=a.id,
                question_id=q.id,
                question=q.question,
                expected_answers=[str(x) for x in q.correct_answers],
                submitted_answer=a.submitted_answer,
                submitted_at=a.submitted_at,
            )
            for a, q in rows
        ]
    )


@router.post("/{misconception_id}/dismiss", response_model=MisconceptionResponse)
async def dismiss(
    misconception_id: uuid.UUID, current_user: ActiveUser, db: DbSession
) -> MisconceptionResponse:
    row = await MisconceptionReview(db).decide(current_user.id, misconception_id, "dismissed")
    return MisconceptionResponse(data=await _one(db, current_user.id, row))


@router.post("/{misconception_id}/confirm", response_model=MisconceptionResponse)
async def confirm(
    misconception_id: uuid.UUID, current_user: ActiveUser, db: DbSession
) -> MisconceptionResponse:
    row = await MisconceptionReview(db).decide(current_user.id, misconception_id, "confirmed")
    return MisconceptionResponse(data=await _one(db, current_user.id, row))


@router.patch("/{misconception_id}", response_model=MisconceptionResponse)
async def correct(
    misconception_id: uuid.UUID, body: MisconceptionPatch, current_user: ActiveUser, db: DbSession
) -> MisconceptionResponse:
    """Fix the wording where the system got it wrong; the result is marked as corrected."""
    row = await MisconceptionReview(db).correct(
        current_user.id,
        misconception_id,
        body.description,
        body.explanation,
        body.recommended_action,
    )
    return MisconceptionResponse(data=await _one(db, current_user.id, row))
