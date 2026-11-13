"""Learner Intelligence dashboard (Phase 6 M6.9). One read-only, owner-scoped endpoint. Every
figure is a count of stored concept states; unassessed concepts are never reported as weak."""

import uuid
from collections import Counter
from datetime import UTC, datetime

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.dependencies import ActiveUser, DbSession
from app.knowledge import dashboard as calc
from app.repositories.learner_dashboard_repository import LearnerDashboardRepository
from app.repositories.recommendation_repository import LEARNER, RecommendationRepository

router = APIRouter(prefix="/knowledge/learner", tags=["knowledge-learner"])


class LearnerOverviewOut(BaseModel):
    tracked: int
    assessed: int
    sufficient_evidence: int
    strong: int
    proficient: int
    developing: int
    weak: int
    insufficient_evidence: int
    unassessed: int
    misconceptions: int
    recommendations: int


class LearnerSubjectOut(BaseModel):
    subject_id: uuid.UUID | None
    subject_name: str | None
    total: int
    assessed: int
    distribution: dict[str, int]
    weak: list[str]
    strong: list[str]
    unassessed: int
    missing_prerequisites: int


class LearnerConceptRowOut(BaseModel):
    node_id: uuid.UUID
    name: str
    subject_id: uuid.UUID | None
    subject_name: str | None
    state: str
    mastery: float | None
    confidence: float
    evidence_count: int
    connections: int


class LearnerGapConceptOut(BaseModel):
    node_id: uuid.UUID
    name: str
    subject_id: uuid.UUID | None
    subject_name: str | None
    state: str
    mastery: float | None
    # missing prerequisites: "demonstrated" (weak/developing) or "no_evidence" (never assessed)
    kind: str | None = None
    needed_for: list[str] = []
    evidence_count: int | None = None
    connections: int | None = None
    next_review_at: datetime | None = None


class LearnerGapMisconceptionOut(BaseModel):
    id: uuid.UUID
    node_id: uuid.UUID
    name: str
    description: str
    confidence: float
    tentative: bool
    evidence_count: int
    status: str


class LearnerGapsOut(BaseModel):
    weak: list[LearnerGapConceptOut]
    missing_prerequisites: list[LearnerGapConceptOut]
    misconceptions: list[LearnerGapMisconceptionOut]
    unassessed_important: list[LearnerGapConceptOut]
    needs_revision: list[LearnerGapConceptOut]


class LearnerDashboardOut(BaseModel):
    overview: LearnerOverviewOut
    subjects: list[LearnerSubjectOut]
    concepts: list[LearnerConceptRowOut]
    gaps: LearnerGapsOut
    note: str


class LearnerDashboardResponse(BaseModel):
    success: bool = True
    data: LearnerDashboardOut


NOTE = (
    "Counts come from your quiz and flashcard results. A concept with no results is shown as "
    "unassessed, which means missing evidence, not weakness."
)


@router.get("/dashboard", response_model=LearnerDashboardResponse)
async def dashboard(
    current_user: ActiveUser,
    db: DbSession,
    workspace_id: uuid.UUID | None = None,
    subject_id: uuid.UUID | None = None,
) -> LearnerDashboardResponse:
    repo = LearnerDashboardRepository(db)
    concepts = await repo.concepts(current_user.id, workspace_id, subject_id)
    ids = {c.id for c in concepts}
    edges = [e for e in await repo.edges(current_user.id) if e[0] in ids and e[1] in ids]
    miscs = [m for m in await repo.misconceptions(current_user.id) if m.node_id in ids]
    pending = [
        r
        for r in await RecommendationRepository(db).pending(current_user.id, LEARNER)
        if r.knowledge_node_id is None or r.knowledge_node_id in ids
    ]
    g = calc.gaps(concepts, edges, miscs, datetime.now(UTC))
    per_subject = Counter(p["subject_id"] for p in g["missing_prerequisites"])
    g["missing_prerequisites"] = g["missing_prerequisites"][: calc.LIST_CAP]
    return LearnerDashboardResponse(
        data=LearnerDashboardOut(
            overview=LearnerOverviewOut(**calc.overview(concepts, len(miscs), len(pending))),
            subjects=[LearnerSubjectOut(**s) for s in calc.subjects(concepts, dict(per_subject))],
            concepts=[
                LearnerConceptRowOut(
                    node_id=c.id,
                    name=c.name,
                    subject_id=c.subject_id,
                    subject_name=c.subject_name,
                    state=c.state,
                    mastery=c.mastery,
                    confidence=c.confidence,
                    evidence_count=c.evidence_count,
                    connections=c.degree,
                )
                for c in concepts
            ],
            gaps=LearnerGapsOut(**g),
            note=NOTE,
        )
    )
