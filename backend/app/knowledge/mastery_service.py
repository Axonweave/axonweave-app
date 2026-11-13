"""Recalculates stored learner concept states from learner evidence (Milestone 6.6, spec 14.5).

The calculation itself is the pure function in `app.knowledge.mastery`; this service only gathers
the evidence snapshot, runs it and stores the result with a plain-language explanation. It never
creates evidence, so recalculating twice gives the same state (reproducible)."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.mastery import CALCULATION_VERSION, EvidenceItem, calculate, describe
from app.models.learner import LearnerConceptState, LearnerEvidence
from app.repositories.learner_state_repository import LearnerStateRepository


def _item(row: LearnerEvidence) -> EvidenceItem:
    meta: dict[str, Any] = row.evidence_metadata or {}
    return EvidenceItem(
        id=str(row.source_event_id),
        source_type=row.source_type,
        value=float(row.evidence_value),
        occurred_at=row.occurred_at,
        difficulty=meta.get("difficulty"),
        ai_assisted=bool(meta.get("ai_assisted")),
        rating=meta.get("rating"),
        lapses=meta.get("lapses"),
    )


class MasteryService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._r = LearnerStateRepository(db)

    async def recalculate(
        self,
        user_id: uuid.UUID,
        node_ids: Iterable[uuid.UUID] | None = None,
        now: datetime | None = None,
    ) -> int:
        """Recompute the state of the given concepts, or of every concept that has evidence or an
        existing state. The caller commits. Returns the number of states written."""
        now = now or datetime.now(UTC)
        if node_ids is None:
            targets = await self._r.target_nodes(user_id)
        else:
            targets = sorted(set(node_ids), key=str)
        nodes = await self._r.nodes(user_id, targets)
        evidence = await self._r.evidence_for(user_id, list(nodes))
        due = await self._r.next_review(user_id, list(nodes))
        written = 0
        for node_id, node in nodes.items():
            result = calculate([_item(e) for e in evidence.get(node_id, [])], now)
            explanation = {**result.explanation, "text": describe(node.name, result)}
            await self._r.upsert(user_id, node, result, due.get(node_id), explanation)
            written += 1
        return written

    async def stale_version_count(self, user_id: uuid.UUID) -> int:
        """States calculated by an older model version (they need a bulk recalculation)."""
        return int(
            (
                await self._db.execute(
                    select(func.count())
                    .select_from(LearnerConceptState)
                    .where(
                        LearnerConceptState.user_id == user_id,
                        LearnerConceptState.calculation_version != CALCULATION_VERSION,
                    )
                )
            ).scalar_one()
        )
