"""Recommendation routes (Phase 5 spec 5.5). Rule-based and owner-scoped; a foreign id is a 404."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.core.dependencies import ActiveUser, DbSession
from app.models.revision import RevisionRecommendation
from app.modules.recommendations.service import RecommendationService

router = APIRouter(prefix="/recommendations", tags=["recommendations"])
AppSettings = Annotated[Settings, Depends(get_settings)]


class RecommendationOut(BaseModel):
    id: uuid.UUID
    recommendation_type: Literal["quiz", "flashcard", "topic", "chapter"]
    topic_name: str | None
    reason: str
    priority: Literal["low", "medium", "high"]
    status: Literal["pending", "completed", "dismissed"]
    created_at: datetime
    completed_at: datetime | None


class RecommendationListOut(BaseModel):
    items: list[RecommendationOut]
    note: str


class RecommendationListResponse(BaseModel):
    success: bool = True
    data: RecommendationListOut


class RecommendationResponse(BaseModel):
    success: bool = True
    data: RecommendationOut


class WeakTopicOut(BaseModel):
    topic: str
    accuracy: float | None
    answers: int
    trend: str | None


class WeakTopicListOut(BaseModel):
    items: list[WeakTopicOut]
    note: str


class WeakTopicListResponse(BaseModel):
    success: bool = True
    data: WeakTopicListOut


NOTE = (
    "Suggestions come from simple rules over your own quiz and flashcard history. They are "
    "prompts, not a measure of what you know."
)


def _out(r: RevisionRecommendation) -> RecommendationOut:
    return RecommendationOut(
        id=r.id,
        recommendation_type=r.recommendation_type,  # type: ignore[arg-type]
        topic_name=r.topic_name,
        reason=r.reason,
        priority=r.priority,  # type: ignore[arg-type]
        status=r.status,  # type: ignore[arg-type]
        created_at=r.created_at,
        completed_at=r.completed_at,
    )


@router.get("/revision", response_model=RecommendationListResponse)
async def revision_recommendations(
    user: ActiveUser, db: DbSession, settings: AppSettings
) -> RecommendationListResponse:
    rows = await RecommendationService(db, settings).sync(user)
    return RecommendationListResponse(
        data=RecommendationListOut(items=[_out(r) for r in rows], note=NOTE)
    )


@router.get("/weak-topics", response_model=WeakTopicListResponse)
async def weak_topics(
    user: ActiveUser, db: DbSession, settings: AppSettings
) -> WeakTopicListResponse:
    items = await RecommendationService(db, settings).weak_topics(user)
    await db.commit()
    return WeakTopicListResponse(
        data=WeakTopicListOut(items=[WeakTopicOut(**i) for i in items], note=NOTE)
    )


@router.post("/{recommendation_id}/complete", response_model=RecommendationResponse)
async def complete(
    recommendation_id: uuid.UUID, user: ActiveUser, db: DbSession, settings: AppSettings
) -> RecommendationResponse:
    rec = await RecommendationService(db, settings).resolve(user, recommendation_id, "completed")
    return RecommendationResponse(data=_out(rec))


@router.post("/{recommendation_id}/dismiss", response_model=RecommendationResponse)
async def dismiss(
    recommendation_id: uuid.UUID, user: ActiveUser, db: DbSession, settings: AppSettings
) -> RecommendationResponse:
    rec = await RecommendationService(db, settings).resolve(user, recommendation_id, "dismissed")
    return RecommendationResponse(data=_out(rec))
