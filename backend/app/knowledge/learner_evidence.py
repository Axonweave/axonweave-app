"""Learner evidence ingestion and concept mapping (Milestone 6.5, spec section 13).

Evidence comes only from per-answer quiz results and per-card flashcard reviews: attempt-level
scores and analytics aggregates are never ingested, so one event is never counted twice (13.5). The
canonical event id is `quiz_attempt_answers.id` or `flashcard_reviews.id`; ingestion is idempotent
through partial unique indexes.

Mapping a question or card to a concept is deliberately conservative (13.2): an exact normalised
match of its `topic` to one concept name or alias is `confirmed`; several matches, or a single
concept whose extraction evidence cites the same document passage, are only `proposed` for review;
a weak similarity score is never used. Only confirmed links give per-concept evidence. Everything
else stays unmapped (concept NULL) and is attached later when a link is confirmed or a matching
concept appears.

Evidence values are 0..1. Quiz answers use awarded/max score. Flashcard ratings use the fixed
recall-quality values below; they are inputs only. The weighting that turns evidence into mastery
is defined and justified in the mastery engine (Milestone 6.6).
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.errors import ConceptLinkNotFoundError
from app.knowledge.mastery_service import MasteryService
from app.knowledge.normalise import normalise_name
from app.models.learner import KnowledgeConceptLink
from app.repositories.learner_evidence_repository import LearnerEvidenceRepository

FLASHCARD_RATING_VALUE: dict[str, Decimal] = {
    "again": Decimal("0.000"),
    "hard": Decimal("0.500"),
    "good": Decimal("0.850"),
    "easy": Decimal("1.000"),
}
SYNC_BATCH = 500
REMAP_BATCH = 200


def _value(awarded: Decimal, maximum: Decimal) -> Decimal:
    if maximum <= 0:
        return Decimal("0.000")
    return max(Decimal("0"), min(Decimal("1"), awarded / maximum)).quantize(Decimal("0.001"))


def _rows(base: dict[str, Any], nodes: list[uuid.UUID]) -> list[dict[str, Any]]:
    if not nodes:
        return [{**base, "knowledge_node_id": None}]
    return [{**base, "knowledge_node_id": n} for n in nodes]


class LearnerEvidenceService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._r = LearnerEvidenceRepository(db)
        # concepts whose evidence changed; their mastery is recalculated before commit (14.5)
        self._touched: set[uuid.UUID] = set()

    # mapping ─────────────────────────────────────────────────────────────────

    async def ensure_links(
        self,
        user_id: uuid.UUID,
        workspace_id: uuid.UUID,
        source_type: str,
        source_id: uuid.UUID,
        topic: str | None,
        refs: list[dict[str, Any]],
    ) -> None:
        """Create links for a question or card that has none yet. Decisions are remembered, so a
        rejected link is never proposed again."""
        if await self._r.links_for(user_id, source_type, source_id):
            return
        matches = []
        if topic and topic.strip():
            matches = await self._r.nodes_by_topic(user_id, workspace_id, normalise_name(topic))
        base = {
            "user_id": user_id,
            "workspace_id": workspace_id,
            "source_type": source_type,
            "source_id": source_id,
        }
        if len(matches) == 1:
            node, method = matches[0]
            await self._r.add_link(
                **base, knowledge_node_id=node.id, method=method, status="confirmed"
            )
        elif len(matches) > 1:
            for node, method in matches:
                await self._r.add_link(
                    **base, knowledge_node_id=node.id, method=method, status="proposed"
                )
        else:
            cited = await self._r.nodes_citing(user_id, workspace_id, refs)
            if len(cited) == 1:
                await self._r.add_link(
                    **base, knowledge_node_id=cited[0], method="source_reference", status="proposed"
                )

    async def _confirmed_nodes(
        self, user_id: uuid.UUID, source_type: str, source_id: uuid.UUID
    ) -> list[uuid.UUID]:
        links = await self._r.links_for(user_id, source_type, source_id)
        return sorted((x.knowledge_node_id for x in links if x.status == "confirmed"), key=str)

    # ingestion ───────────────────────────────────────────────────────────────

    async def sync(self, user_id: uuid.UUID) -> dict[str, int]:
        """Ingest events that have no evidence yet, then retry mapping for unmapped sources.
        Idempotent and bounded; call again while `more` is 1."""
        added = 0
        cache: dict[tuple[str, uuid.UUID], list[uuid.UUID]] = {}

        async def nodes_for(
            ws: uuid.UUID,
            stype: str,
            sid: uuid.UUID,
            topic: str | None,
            refs: list[dict[str, Any]],
        ) -> list[uuid.UUID]:
            key = (stype, sid)
            if key not in cache:
                await self.ensure_links(user_id, ws, stype, sid, topic, refs)
                cache[key] = await self._confirmed_nodes(user_id, stype, sid)
                self._touched.update(cache[key])
            return cache[key]

        answers = await self._r.new_quiz_answers(user_id, SYNC_BATCH)
        for ans, question, attempt, ws in answers:
            nodes = await nodes_for(
                ws, "quiz_question", question.id, question.topic, question.source_references
            )
            base = {
                "user_id": user_id,
                "workspace_id": ws,
                "source_type": "quiz_answer",
                "source_id": question.id,
                "source_event_id": ans.id,
                "topic": question.topic,
                "evidence_value": _value(ans.awarded_score, ans.max_score),
                "evidence_metadata": {
                    "attempt_id": str(attempt.id),
                    "quiz_id": str(question.quiz_id),
                    "question_type": question.question_type,
                    "difficulty": question.difficulty,
                    "correct": ans.is_correct,
                    "awarded_score": float(ans.awarded_score),
                    "max_score": float(ans.max_score),
                    "grading_method": ans.grading_method,
                    "ai_assisted": ans.ai_assisted,
                },
                "occurred_at": ans.submitted_at,
            }
            added += await self._r.add_evidence(_rows(base, nodes))

        reviews = await self._r.new_flashcard_reviews(user_id, SYNC_BATCH)
        for rev, card, ws in reviews:
            nodes = await nodes_for(ws, "flashcard", card.id, card.topic, card.source_references)
            resulting = rev.resulting_state or {}
            base = {
                "user_id": user_id,
                "workspace_id": ws,
                "source_type": "flashcard_review",
                "source_id": card.id,
                "source_event_id": rev.id,
                "topic": card.topic,
                "evidence_value": FLASHCARD_RATING_VALUE.get(rev.rating, Decimal("0.000")),
                "evidence_metadata": {
                    "rating": rev.rating,
                    "card_type": card.card_type,
                    "difficulty": card.difficulty,
                    "elapsed_days": rev.elapsed_days,
                    "scheduled_days": rev.scheduled_days,
                    "response_time_ms": rev.response_time_ms,
                    "lapses": resulting.get("lapses"),
                    "state": resulting.get("state"),
                    "scheduler_version": rev.scheduler_version,
                },
                "occurred_at": rev.reviewed_at,
            }
            added += await self._r.add_evidence(_rows(base, nodes))

        remapped = await self.remap_unresolved(user_id)
        await MasteryService(self._db).recalculate(user_id, self._touched)
        await self._db.commit()
        return {
            "ingested": added,
            "remapped": remapped,
            "more": int(len(answers) >= SYNC_BATCH or len(reviews) >= SYNC_BATCH),
        }

    # re-mapping ──────────────────────────────────────────────────────────────

    async def remap_unresolved(self, user_id: uuid.UUID) -> int:
        """Retry mapping for sources whose evidence is unmapped (a matching concept may exist now)
        and apply it. Returns the number of evidence rows newly attached to a concept."""
        attached = 0
        for link_type, sid, ws, topic, refs in await self._r.unmapped_sources(user_id, REMAP_BATCH):
            await self.ensure_links(user_id, ws, link_type, sid, topic, refs)
            attached += await self.reconcile(user_id, link_type, sid)
        return attached

    async def reconcile(self, user_id: uuid.UUID, link_type: str, source_id: uuid.UUID) -> int:
        """Make the evidence of one question/card match its confirmed links: one row per event and
        confirmed concept, or one unmapped row when none is confirmed. Returns rows newly attached
        to a concept."""
        ev_type = "quiz_answer" if link_type == "quiz_question" else "flashcard_review"
        confirmed: set[uuid.UUID | None] = set(
            await self._confirmed_nodes(user_id, link_type, source_id)
        )
        target: set[uuid.UUID | None] = confirmed or {None}
        by_event: dict[uuid.UUID, list[Any]] = {}
        for row in await self._r.events_of_source(user_id, ev_type, source_id):
            by_event.setdefault(row.source_event_id, []).append(row)
        attached = 0
        for event_id, existing in by_event.items():
            dropped = [r for r in existing if r.knowledge_node_id not in target]
            self._touched.update(r.knowledge_node_id for r in dropped if r.knowledge_node_id)
            await self._r.delete_evidence_ids(user_id, [r.id for r in dropped])
            have = {r.knowledge_node_id for r in existing}
            t = existing[0]
            fresh = [
                {
                    "user_id": user_id,
                    "workspace_id": t.workspace_id,
                    "knowledge_node_id": n,
                    "source_type": ev_type,
                    "source_id": source_id,
                    "source_event_id": event_id,
                    "topic": t.topic,
                    "evidence_value": t.evidence_value,
                    "evidence_metadata": t.evidence_metadata,
                    "occurred_at": t.occurred_at,
                }
                for n in target - have
            ]
            self._touched.update(n for n in target - have if n is not None)
            if await self._r.add_evidence(fresh):
                attached += sum(1 for f in fresh if f["knowledge_node_id"] is not None)
        return attached

    # review decisions ────────────────────────────────────────────────────────

    async def decide_link(
        self, user_id: uuid.UUID, link_id: uuid.UUID, status: str
    ) -> KnowledgeConceptLink:
        link = await self._r.get_link(user_id, link_id)
        if link is None:
            raise ConceptLinkNotFoundError()
        link.status = status
        if status == "confirmed" and link.method == "source_reference":
            link.method = "user"
        await self._db.flush()
        await self.reconcile(user_id, link.source_type, link.source_id)
        self._touched.add(link.knowledge_node_id)
        await MasteryService(self._db).recalculate(user_id, self._touched)
        await self._db.commit()
        await self._db.refresh(link)
        return link
