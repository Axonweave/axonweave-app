"""Persistence for learner concept states (Milestone 6.6). Every query is filtered by `user_id`."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.mastery import MasteryResult
from app.models.knowledge import KnowledgeNode
from app.models.learner import KnowledgeConceptLink, LearnerConceptState, LearnerEvidence
from app.models.revision import FlashcardScheduling


class LearnerStateRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def target_nodes(self, user_id: uuid.UUID) -> list[uuid.UUID]:
        """Concepts that have evidence or an existing state (so lost evidence resets it)."""
        with_ev = select(LearnerEvidence.knowledge_node_id).where(
            LearnerEvidence.user_id == user_id, LearnerEvidence.knowledge_node_id.is_not(None)
        )
        with_state = select(LearnerConceptState.knowledge_node_id).where(
            LearnerConceptState.user_id == user_id
        )
        rows = await self._db.execute(with_ev.union(with_state))
        return sorted((r for (r,) in rows.all() if r is not None), key=str)

    async def nodes(
        self, user_id: uuid.UUID, node_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, KnowledgeNode]:
        if not node_ids:
            return {}
        rows = await self._db.execute(
            select(KnowledgeNode).where(
                KnowledgeNode.user_id == user_id, KnowledgeNode.id.in_(node_ids)
            )
        )
        return {n.id: n for n in rows.scalars()}

    async def evidence_for(
        self, user_id: uuid.UUID, node_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, list[LearnerEvidence]]:
        out: dict[uuid.UUID, list[LearnerEvidence]] = {}
        if not node_ids:
            return out
        rows = await self._db.execute(
            select(LearnerEvidence).where(
                LearnerEvidence.user_id == user_id,
                LearnerEvidence.knowledge_node_id.in_(node_ids),
            )
        )
        for row in rows.scalars():
            if row.knowledge_node_id is not None:
                out.setdefault(row.knowledge_node_id, []).append(row)
        return out

    async def next_review(
        self, user_id: uuid.UUID, node_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, datetime]:
        """Earliest due time of an active flashcard confirmed as covering the concept."""
        if not node_ids:
            return {}
        rows = await self._db.execute(
            select(KnowledgeConceptLink.knowledge_node_id, func.min(FlashcardScheduling.due_at))
            .join(
                FlashcardScheduling,
                (FlashcardScheduling.flashcard_id == KnowledgeConceptLink.source_id)
                & (FlashcardScheduling.user_id == KnowledgeConceptLink.user_id),
            )
            .where(
                KnowledgeConceptLink.user_id == user_id,
                KnowledgeConceptLink.source_type == "flashcard",
                KnowledgeConceptLink.status == "confirmed",
                KnowledgeConceptLink.knowledge_node_id.in_(node_ids),
                FlashcardScheduling.suspended.is_(False),
            )
            .group_by(KnowledgeConceptLink.knowledge_node_id)
        )
        return {n: due for n, due in rows.all()}  # noqa: C416

    async def upsert(
        self,
        user_id: uuid.UUID,
        node: KnowledgeNode,
        result: MasteryResult,
        next_review_at: datetime | None,
        explanation: dict[str, Any],
    ) -> None:
        values = {
            "workspace_id": node.workspace_id,
            "mastery_estimate": (None if result.mastery is None else Decimal(str(result.mastery))),
            "confidence": Decimal(str(result.confidence)),
            "evidence_count": result.evidence_count,
            "state": result.state,
            "last_evidence_at": result.last_evidence_at,
            "next_review_at": next_review_at,
            "calculation_version": result.version,
            "explanation": explanation,
        }
        stmt = pg_insert(LearnerConceptState).values(
            id=uuid.uuid4(), user_id=user_id, knowledge_node_id=node.id, **values
        )
        await self._db.execute(
            stmt.on_conflict_do_update(
                constraint="uq_learner_states_user_node",
                set_={**values, "updated_at": func.now()},
            )
        )

    async def get(self, user_id: uuid.UUID, node_id: uuid.UUID) -> LearnerConceptState | None:
        return (
            await self._db.execute(
                select(LearnerConceptState).where(
                    LearnerConceptState.user_id == user_id,
                    LearnerConceptState.knowledge_node_id == node_id,
                )
            )
        ).scalar_one_or_none()

    async def list_states(
        self,
        user_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID | None,
        state: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[tuple[LearnerConceptState, str]], int]:
        conds = [LearnerConceptState.user_id == user_id, KnowledgeNode.archived_at.is_(None)]
        if workspace_id:
            conds.append(LearnerConceptState.workspace_id == workspace_id)
        if state:
            conds.append(LearnerConceptState.state == state)
        base = select(LearnerConceptState, KnowledgeNode.name).join(
            KnowledgeNode, KnowledgeNode.id == LearnerConceptState.knowledge_node_id
        )
        total = (
            await self._db.execute(
                select(func.count())
                .select_from(LearnerConceptState)
                .join(KnowledgeNode, KnowledgeNode.id == LearnerConceptState.knowledge_node_id)
                .where(*conds)
            )
        ).scalar_one()
        rows = await self._db.execute(
            base.where(*conds)
            .order_by(LearnerConceptState.mastery_estimate.asc().nulls_last(), KnowledgeNode.name)
            .limit(limit)
            .offset(offset)
        )
        return [(s, n) for s, n in rows.all()], int(total)  # noqa: C416
