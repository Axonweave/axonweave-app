"""Facts for the Learner Intelligence dashboard (Milestone 6.9). Read-only, owner-scoped and
bounded. Concepts without a learner state row are reported as NOT_ASSESSED with no score."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeEdge, KnowledgeNode
from app.models.learner import LearnerConceptState, LearnerMisconception
from app.models.subject import Subject

MAX_NODES = 2000
MAX_EDGES = 5000
ACTIVE_MISCONCEPTIONS = ("suggested", "confirmed", "corrected")


@dataclass(frozen=True)
class DashConcept:
    id: uuid.UUID
    name: str
    workspace_id: uuid.UUID
    subject_id: uuid.UUID | None
    subject_name: str | None
    state: str
    mastery: float | None
    confidence: float
    evidence_count: int
    next_review_at: datetime | None
    degree: int


@dataclass(frozen=True)
class DashMisconception:
    id: uuid.UUID
    node_id: uuid.UUID
    description: str
    confidence: float
    evidence_count: int
    status: str


class LearnerDashboardRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def concepts(
        self, user_id: uuid.UUID, workspace_id: uuid.UUID | None, subject_id: uuid.UUID | None
    ) -> list[DashConcept]:
        degree = (
            select(func.count())
            .select_from(KnowledgeEdge)
            .where(
                KnowledgeEdge.user_id == user_id,
                or_(
                    KnowledgeEdge.source_node_id == KnowledgeNode.id,
                    KnowledgeEdge.target_node_id == KnowledgeNode.id,
                ),
            )
            .correlate(KnowledgeNode)
            .scalar_subquery()
        )
        conds = [KnowledgeNode.user_id == user_id, KnowledgeNode.archived_at.is_(None)]
        if workspace_id:
            conds.append(KnowledgeNode.workspace_id == workspace_id)
        if subject_id:
            conds.append(KnowledgeNode.subject_id == subject_id)
        rows = await self._db.execute(
            select(KnowledgeNode, LearnerConceptState, Subject.name, degree)
            .outerjoin(
                LearnerConceptState,
                (LearnerConceptState.knowledge_node_id == KnowledgeNode.id)
                & (LearnerConceptState.user_id == KnowledgeNode.user_id),
            )
            .outerjoin(Subject, Subject.id == KnowledgeNode.subject_id)
            .where(*conds)
            .order_by(KnowledgeNode.name, KnowledgeNode.id)
            .limit(MAX_NODES)
        )
        return [
            DashConcept(
                id=n.id,
                name=n.name,
                workspace_id=n.workspace_id,
                subject_id=n.subject_id,
                subject_name=subject,
                state=s.state if s is not None else "NOT_ASSESSED",
                mastery=None
                if s is None or s.mastery_estimate is None
                else float(s.mastery_estimate),
                confidence=float(s.confidence) if s is not None else 0.0,
                evidence_count=s.evidence_count if s is not None else 0,
                next_review_at=s.next_review_at if s is not None else None,
                degree=int(deg or 0),
            )
            for n, s, subject, deg in rows.all()
        ]

    async def edges(self, user_id: uuid.UUID) -> list[tuple[uuid.UUID, uuid.UUID, str]]:
        rows = await self._db.execute(
            select(
                KnowledgeEdge.source_node_id,
                KnowledgeEdge.target_node_id,
                KnowledgeEdge.relationship_type,
            )
            .where(
                KnowledgeEdge.user_id == user_id,
                KnowledgeEdge.relationship_type.in_(("PREREQUISITE_OF", "DEPENDS_ON")),
            )
            .limit(MAX_EDGES)
        )
        return [(s, t, ty) for s, t, ty in rows.tuples().all()]  # noqa: C416

    async def misconceptions(self, user_id: uuid.UUID) -> list[DashMisconception]:
        rows = await self._db.execute(
            select(LearnerMisconception)
            .where(
                LearnerMisconception.user_id == user_id,
                LearnerMisconception.status.in_(ACTIVE_MISCONCEPTIONS),
            )
            .order_by(LearnerMisconception.confidence.desc(), LearnerMisconception.id)
            .limit(200)
        )
        return [
            DashMisconception(
                m.id,
                m.knowledge_node_id,
                m.description,
                float(m.confidence),
                m.evidence_count,
                m.status,
            )
            for m in rows.scalars()
        ]
