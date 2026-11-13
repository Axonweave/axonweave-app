"""Facts for learner recommendations (Milestone 6.8). Read-only and owner-scoped; every list is
capped so a large graph cannot make a request unbounded."""

from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.recommendations import ConceptFacts, Edge, MisconceptionFacts
from app.models.chapter import Chapter
from app.models.knowledge import KnowledgeEdge, KnowledgeNode
from app.models.learner import LearnerConceptState, LearnerEvidence, LearnerMisconception

MAX_NODES = 2000
MAX_EDGES = 5000
RELEVANT_EDGES = ("PREREQUISITE_OF", "DEPENDS_ON", "RELATED_TO")


class LearnerRecommendationRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def concepts(self, user_id: uuid.UUID) -> list[ConceptFacts]:
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
        rows = await self._db.execute(
            select(KnowledgeNode, LearnerConceptState, Chapter.title, degree)
            .outerjoin(
                LearnerConceptState,
                (LearnerConceptState.knowledge_node_id == KnowledgeNode.id)
                & (LearnerConceptState.user_id == KnowledgeNode.user_id),
            )
            .outerjoin(Chapter, Chapter.id == KnowledgeNode.chapter_id)
            .where(KnowledgeNode.user_id == user_id, KnowledgeNode.archived_at.is_(None))
            .order_by(KnowledgeNode.name, KnowledgeNode.id)
            .limit(MAX_NODES)
        )
        hard = await self._hard_failures(user_id)
        out: list[ConceptFacts] = []
        for node, st, chapter_title, deg in rows.all():
            out.append(
                ConceptFacts(
                    id=node.id,
                    name=node.name,
                    state=st.state if st is not None else "NOT_ASSESSED",
                    mastery=None
                    if st is None or st.mastery_estimate is None
                    else float(st.mastery_estimate),
                    confidence=float(st.confidence) if st is not None else 0.0,
                    evidence_count=st.evidence_count if st is not None else 0,
                    next_review_at=st.next_review_at if st is not None else None,
                    chapter_id=node.chapter_id,
                    chapter_title=chapter_title,
                    degree=int(deg or 0),
                    hard_failures=hard.get(node.id, 0),
                )
            )
        return out

    async def _hard_failures(self, user_id: uuid.UUID) -> dict[uuid.UUID, int]:
        rows = await self._db.execute(
            select(LearnerEvidence.knowledge_node_id, func.count())
            .where(
                LearnerEvidence.user_id == user_id,
                LearnerEvidence.knowledge_node_id.is_not(None),
                LearnerEvidence.source_type == "quiz_answer",
                LearnerEvidence.evidence_metadata["difficulty"].astext == "hard",
                LearnerEvidence.evidence_value < 0.5,
            )
            .group_by(LearnerEvidence.knowledge_node_id)
        )
        return {n: int(c) for n, c in rows.all() if n is not None}

    async def edges(self, user_id: uuid.UUID) -> list[Edge]:
        rows = await self._db.execute(
            select(
                KnowledgeEdge.source_node_id,
                KnowledgeEdge.target_node_id,
                KnowledgeEdge.relationship_type,
            )
            .where(
                KnowledgeEdge.user_id == user_id,
                KnowledgeEdge.relationship_type.in_(RELEVANT_EDGES),
            )
            .limit(MAX_EDGES)
        )
        return [Edge(s, t, ty) for s, t, ty in rows.all()]

    async def misconceptions(self, user_id: uuid.UUID) -> list[MisconceptionFacts]:
        rows = await self._db.execute(
            select(LearnerMisconception)
            .where(
                LearnerMisconception.user_id == user_id,
                LearnerMisconception.status.in_(("suggested", "confirmed", "corrected")),
            )
            .order_by(LearnerMisconception.confidence.desc(), LearnerMisconception.id)
            .limit(200)
        )
        return [
            MisconceptionFacts(
                id=m.id,
                node_id=m.knowledge_node_id,
                description=m.description,
                confidence=float(m.confidence),
                action=m.recommended_action,
                evidence_count=m.evidence_count,
            )
            for m in rows.scalars()
        ]
