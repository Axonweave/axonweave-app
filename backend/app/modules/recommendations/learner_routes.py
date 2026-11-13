"""Learner recommendation routes (Phase 6 M6.8). Additive: the Phase 5 `/recommendations/*` routes
and their response shapes are unchanged. Owner-scoped; a foreign id is a 404."""

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.dependencies import ActiveUser, DbSession
from app.knowledge.recommendation_service import LearnerRecommendationService
from app.models.revision import RevisionRecommendation

router = APIRouter(prefix="/recommendations/learner", tags=["recommendations"])


class LearnerRecommendationOut(BaseModel):
    id: uuid.UUID
    recommendation_type: str
    knowledge_node_id: uuid.UUID | None
    topic_name: str | None
    reason: str
    suggested_action: str | None
    priority: str
    # documented in app/knowledge/recommendations.py: base score plus an adjustment
    score: float | None
    evidence: dict[str, Any]
    status: str
    created_at: datetime
    completed_at: datetime | None


class LearnerRecommendationListOut(BaseModel):
    items: list[LearnerRecommendationOut]
    note: str


class LearnerRecommendationListResponse(BaseModel):
    success: bool = True
    data: LearnerRecommendationListOut


class LearnerRecommendationResponse(BaseModel):
    success: bool = True
    data: LearnerRecommendationOut


NOTE = (
    "Suggestions come from your quiz and flashcard evidence and the relationships between "
    "concepts. Each shows the facts behind it. They are prompts, not a measure of what you know."
)


def _out(r: RevisionRecommendation) -> LearnerRecommendationOut:
    return LearnerRecommendationOut(
        id=r.id,
        recommendation_type=r.recommendation_type,
        knowledge_node_id=r.knowledge_node_id,
        topic_name=r.topic_name,
        reason=r.reason,
        suggested_action=r.suggested_action,
        priority=r.priority,
        score=None if r.score is None else float(r.score),
        evidence=dict(r.evidence or {}),
        status=r.status,
        created_at=r.created_at,
        completed_at=r.completed_at,
    )


@router.get("", response_model=LearnerRecommendationListResponse)
async def learner_recommendations(
    user: ActiveUser, db: DbSession
) -> LearnerRecommendationListResponse:
    rows = await LearnerRecommendationService(db).sync(user.id)
    return LearnerRecommendationListResponse(
        data=LearnerRecommendationListOut(items=[_out(r) for r in rows], note=NOTE)
    )


@router.post("/{recommendation_id}/complete", response_model=LearnerRecommendationResponse)
async def complete(
    recommendation_id: uuid.UUID, user: ActiveUser, db: DbSession
) -> LearnerRecommendationResponse:
    rec = await LearnerRecommendationService(db).resolve(user.id, recommendation_id, "completed")
    return LearnerRecommendationResponse(data=_out(rec))


@router.post("/{recommendation_id}/dismiss", response_model=LearnerRecommendationResponse)
async def dismiss(
    recommendation_id: uuid.UUID, user: ActiveUser, db: DbSession
) -> LearnerRecommendationResponse:
    rec = await LearnerRecommendationService(db).resolve(user.id, recommendation_id, "dismissed")
    return LearnerRecommendationResponse(data=_out(rec))
