"""Persistence for concept links and learner evidence (Milestone 6.5). Every query is filtered by
`user_id` (rule 3). Phase 5 tables are only read here; nothing in them is changed."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import and_, delete, func, or_, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.flashcard import Flashcard, FlashcardSet
from app.models.knowledge import KnowledgeEvidence, KnowledgeNode
from app.models.learner import KnowledgeConceptLink, LearnerEvidence
from app.models.quiz import Quiz, QuizAttempt, QuizAttemptAnswer, QuizQuestion
from app.models.revision import FlashcardReview
from app.models.study_material import StudyMaterial


class LearnerEvidenceRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # events not yet ingested ─────────────────────────────────────────────────

    async def new_quiz_answers(self, user_id: uuid.UUID, limit: int) -> Sequence[Any]:
        """Graded answers of submitted attempts that have no evidence row yet."""
        seen = (
            select(LearnerEvidence.id)
            .where(
                LearnerEvidence.user_id == user_id,
                LearnerEvidence.source_type == "quiz_answer",
                LearnerEvidence.source_event_id == QuizAttemptAnswer.id,
            )
            .exists()
        )
        rows = await self._db.execute(
            select(QuizAttemptAnswer, QuizQuestion, QuizAttempt, StudyMaterial.workspace_id)
            .join(QuizAttempt, QuizAttempt.id == QuizAttemptAnswer.attempt_id)
            .join(QuizQuestion, QuizQuestion.id == QuizAttemptAnswer.question_id)
            .join(Quiz, Quiz.id == QuizQuestion.quiz_id)
            .join(StudyMaterial, StudyMaterial.id == Quiz.study_material_id)
            .where(
                QuizAttemptAnswer.user_id == user_id,
                QuizAttempt.user_id == user_id,
                QuizAttempt.status == "submitted",
                QuizAttemptAnswer.evaluation_status == "graded",
                QuizAttemptAnswer.max_score > 0,
                ~seen,
            )
            .order_by(QuizAttemptAnswer.submitted_at)
            .limit(limit)
        )
        return rows.all()

    async def new_flashcard_reviews(self, user_id: uuid.UUID, limit: int) -> Sequence[Any]:
        seen = (
            select(LearnerEvidence.id)
            .where(
                LearnerEvidence.user_id == user_id,
                LearnerEvidence.source_type == "flashcard_review",
                LearnerEvidence.source_event_id == FlashcardReview.id,
            )
            .exists()
        )
        rows = await self._db.execute(
            select(FlashcardReview, Flashcard, StudyMaterial.workspace_id)
            .join(Flashcard, Flashcard.id == FlashcardReview.flashcard_id)
            .join(FlashcardSet, FlashcardSet.id == Flashcard.flashcard_set_id)
            .join(StudyMaterial, StudyMaterial.id == FlashcardSet.study_material_id)
            .where(FlashcardReview.user_id == user_id, Flashcard.user_id == user_id, ~seen)
            .order_by(FlashcardReview.reviewed_at)
            .limit(limit)
        )
        return rows.all()

    # concept matching ────────────────────────────────────────────────────────

    async def nodes_by_topic(
        self, user_id: uuid.UUID, workspace_id: uuid.UUID, normalised: str
    ) -> list[tuple[KnowledgeNode, str]]:
        """Active concepts whose normalised name (`exact_name`) or alias (`alias`) equals it."""
        from app.models.knowledge import KnowledgeNodeAlias

        out: dict[uuid.UUID, tuple[KnowledgeNode, str]] = {}
        by_name = await self._db.execute(
            select(KnowledgeNode).where(
                KnowledgeNode.user_id == user_id,
                KnowledgeNode.workspace_id == workspace_id,
                KnowledgeNode.normalised_name == normalised,
                KnowledgeNode.archived_at.is_(None),
            )
        )
        for n in by_name.scalars():
            out[n.id] = (n, "exact_name")
        by_alias = await self._db.execute(
            select(KnowledgeNode)
            .join(
                KnowledgeNodeAlias,
                and_(
                    KnowledgeNodeAlias.knowledge_node_id == KnowledgeNode.id,
                    KnowledgeNodeAlias.user_id == KnowledgeNode.user_id,
                ),
            )
            .where(
                KnowledgeNode.user_id == user_id,
                KnowledgeNode.workspace_id == workspace_id,
                KnowledgeNode.archived_at.is_(None),
                KnowledgeNodeAlias.normalised_alias == normalised,
            )
        )
        for n in by_alias.scalars():
            out.setdefault(n.id, (n, "alias"))
        return list(out.values())

    async def nodes_citing(
        self,
        user_id: uuid.UUID,
        workspace_id: uuid.UUID,
        refs: Sequence[dict[str, Any]],
    ) -> list[uuid.UUID]:
        """Active concepts whose extraction evidence cites the same document chunk or page."""
        conds = []
        for ref in refs:
            try:
                doc = uuid.UUID(str(ref["document_id"]))
            except (KeyError, ValueError):
                continue
            where = [KnowledgeEvidence.document_id == doc]
            sub = []
            if ref.get("chunk_id"):
                try:
                    sub.append(KnowledgeEvidence.chunk_id == uuid.UUID(str(ref["chunk_id"])))
                except ValueError:
                    pass
            if ref.get("page_number") is not None:
                sub.append(KnowledgeEvidence.page_number == int(ref["page_number"]))
            if not sub:
                continue
            conds.append(and_(*where, or_(*sub)))
        if not conds:
            return []
        rows = await self._db.execute(
            select(KnowledgeEvidence.knowledge_node_id)
            .join(KnowledgeNode, KnowledgeNode.id == KnowledgeEvidence.knowledge_node_id)
            .where(
                KnowledgeEvidence.user_id == user_id,
                KnowledgeEvidence.stale.is_(False),
                KnowledgeNode.workspace_id == workspace_id,
                KnowledgeNode.archived_at.is_(None),
                or_(*conds),
            )
            .distinct()
        )
        return [r for (r,) in rows.all() if r is not None]

    # links ───────────────────────────────────────────────────────────────────

    async def links_for(
        self, user_id: uuid.UUID, source_type: str, source_id: uuid.UUID
    ) -> list[KnowledgeConceptLink]:
        rows = await self._db.execute(
            select(KnowledgeConceptLink).where(
                KnowledgeConceptLink.user_id == user_id,
                KnowledgeConceptLink.source_type == source_type,
                KnowledgeConceptLink.source_id == source_id,
            )
        )
        return list(rows.scalars())

    async def add_link(self, **fields: Any) -> None:
        await self._db.execute(
            pg_insert(KnowledgeConceptLink)
            .values(id=uuid.uuid4(), **fields)
            .on_conflict_do_nothing()
        )

    async def get_link(self, user_id: uuid.UUID, link_id: uuid.UUID) -> KnowledgeConceptLink | None:
        return (
            await self._db.execute(
                select(KnowledgeConceptLink).where(
                    KnowledgeConceptLink.id == link_id, KnowledgeConceptLink.user_id == user_id
                )
            )
        ).scalar_one_or_none()

    async def list_links(
        self,
        user_id: uuid.UUID,
        *,
        status: str | None,
        workspace_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[list[tuple[KnowledgeConceptLink, str, str | None]], int]:
        """Links with the concept name and the question/card topic text, for the review queue."""
        conds = [KnowledgeConceptLink.user_id == user_id]
        if status:
            conds.append(KnowledgeConceptLink.status == status)
        if workspace_id:
            conds.append(KnowledgeConceptLink.workspace_id == workspace_id)
        total = (
            await self._db.execute(
                select(func.count()).select_from(KnowledgeConceptLink).where(*conds)
            )
        ).scalar_one()
        rows = await self._db.execute(
            select(KnowledgeConceptLink, KnowledgeNode.name)
            .join(KnowledgeNode, KnowledgeNode.id == KnowledgeConceptLink.knowledge_node_id)
            .where(*conds)
            .order_by(KnowledgeConceptLink.created_at.desc(), KnowledgeConceptLink.id)
            .limit(limit)
            .offset(offset)
        )
        out: list[tuple[KnowledgeConceptLink, str, str | None]] = []
        for link, name in rows.all():
            out.append((link, name, await self._source_label(user_id, link)))
        return out, int(total)

    async def link_labels(
        self, user_id: uuid.UUID, link: KnowledgeConceptLink
    ) -> tuple[str, str | None]:
        name = (
            await self._db.execute(
                select(KnowledgeNode.name).where(
                    KnowledgeNode.id == link.knowledge_node_id, KnowledgeNode.user_id == user_id
                )
            )
        ).scalar_one_or_none()
        return name or "", await self._source_label(user_id, link)

    async def _source_label(self, user_id: uuid.UUID, link: KnowledgeConceptLink) -> str | None:
        if link.source_type == "quiz_question":
            q = (
                await self._db.execute(
                    select(QuizQuestion.question).where(
                        QuizQuestion.id == link.source_id, QuizQuestion.user_id == user_id
                    )
                )
            ).scalar_one_or_none()
        else:
            q = (
                await self._db.execute(
                    select(Flashcard.front).where(
                        Flashcard.id == link.source_id, Flashcard.user_id == user_id
                    )
                )
            ).scalar_one_or_none()
        return q[:200] if q else None

    # evidence ────────────────────────────────────────────────────────────────

    async def add_evidence(self, rows: list[dict[str, Any]]) -> int:
        """Idempotent insert: an event already stored for the same concept is skipped."""
        added = 0
        for row in rows:
            # rowcount is unreliable (-1) for this driver; RETURNING says if a row was inserted
            result = await self._db.execute(
                pg_insert(LearnerEvidence)
                .values(id=uuid.uuid4(), **row)
                .on_conflict_do_nothing()
                .returning(LearnerEvidence.id)
            )
            added += 1 if result.first() is not None else 0
        return added

    async def events_of_source(
        self, user_id: uuid.UUID, source_type: str, source_id: uuid.UUID
    ) -> list[LearnerEvidence]:
        rows = await self._db.execute(
            select(LearnerEvidence).where(
                LearnerEvidence.user_id == user_id,
                LearnerEvidence.source_type == source_type,
                LearnerEvidence.source_id == source_id,
            )
        )
        return list(rows.scalars())

    async def delete_evidence_ids(self, user_id: uuid.UUID, ids: Sequence[uuid.UUID]) -> None:
        if ids:
            await self._db.execute(
                delete(LearnerEvidence).where(
                    LearnerEvidence.user_id == user_id, LearnerEvidence.id.in_(ids)
                )
            )

    async def unmapped_sources(
        self, user_id: uuid.UUID, limit: int
    ) -> list[tuple[str, uuid.UUID, uuid.UUID, str | None, list[dict[str, Any]]]]:
        """Questions/cards with unmapped evidence and no link decision yet, so mapping is retried
        (a matching concept may exist now). Sources that already have a link (proposed, confirmed
        or rejected) are handled by review, not retried here."""
        out: list[tuple[str, uuid.UUID, uuid.UUID, str | None, list[dict[str, Any]]]] = []
        for ev_type, link_type in (
            ("quiz_answer", "quiz_question"),
            ("flashcard_review", "flashcard"),
        ):
            has_link = (
                select(KnowledgeConceptLink.id)
                .where(
                    KnowledgeConceptLink.user_id == user_id,
                    KnowledgeConceptLink.source_type == link_type,
                    KnowledgeConceptLink.source_id == LearnerEvidence.source_id,
                )
                .exists()
            )
            rows = await self._db.execute(
                select(
                    LearnerEvidence.source_id, LearnerEvidence.workspace_id, LearnerEvidence.topic
                )
                .where(
                    LearnerEvidence.user_id == user_id,
                    LearnerEvidence.source_type == ev_type,
                    LearnerEvidence.knowledge_node_id.is_(None),
                    ~has_link,
                )
                .distinct()
                .limit(limit)
            )
            for sid, ws, topic in rows.all():
                if link_type == "quiz_question":
                    refs = (
                        await self._db.execute(
                            select(QuizQuestion.source_references).where(
                                QuizQuestion.id == sid, QuizQuestion.user_id == user_id
                            )
                        )
                    ).scalar_one_or_none()
                else:
                    refs = (
                        await self._db.execute(
                            select(Flashcard.source_references).where(
                                Flashcard.id == sid, Flashcard.user_id == user_id
                            )
                        )
                    ).scalar_one_or_none()
                out.append((link_type, sid, ws, topic, list(refs or [])))
        return out

    async def list_evidence(
        self,
        user_id: uuid.UUID,
        *,
        node_id: uuid.UUID | None,
        unmapped: bool,
        workspace_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[list[LearnerEvidence], int]:
        conds = [LearnerEvidence.user_id == user_id]
        if node_id:
            conds.append(LearnerEvidence.knowledge_node_id == node_id)
        if unmapped:
            conds.append(LearnerEvidence.knowledge_node_id.is_(None))
        if workspace_id:
            conds.append(LearnerEvidence.workspace_id == workspace_id)
        total = (
            await self._db.execute(select(func.count()).select_from(LearnerEvidence).where(*conds))
        ).scalar_one()
        rows = await self._db.execute(
            select(LearnerEvidence)
            .where(*conds)
            .order_by(LearnerEvidence.occurred_at.desc(), LearnerEvidence.id)
            .limit(limit)
            .offset(offset)
        )
        return list(rows.scalars()), int(total)

    async def summary(self, user_id: uuid.UUID) -> dict[str, int]:
        total = (
            await self._db.execute(
                select(func.count())
                .select_from(LearnerEvidence)
                .where(LearnerEvidence.user_id == user_id)
            )
        ).scalar_one()
        unmapped = (
            await self._db.execute(
                select(func.count())
                .select_from(LearnerEvidence)
                .where(
                    LearnerEvidence.user_id == user_id, LearnerEvidence.knowledge_node_id.is_(None)
                )
            )
        ).scalar_one()
        proposed = (
            await self._db.execute(
                select(func.count())
                .select_from(KnowledgeConceptLink)
                .where(
                    KnowledgeConceptLink.user_id == user_id,
                    KnowledgeConceptLink.status == "proposed",
                )
            )
        ).scalar_one()
        return {"total": int(total), "unmapped": int(unmapped), "proposed_links": int(proposed)}

    # merge support ───────────────────────────────────────────────────────────

    async def repoint_node(
        self, user_id: uuid.UUID, from_node: uuid.UUID, to_node: uuid.UUID
    ) -> tuple[int, int]:
        """Move links and evidence of a merged concept to the survivor. Rows that would collide
        with one the survivor already has are dropped (same event or same source, same concept)."""
        moved_links = moved_ev = 0
        existing_sources = select(
            KnowledgeConceptLink.source_type, KnowledgeConceptLink.source_id
        ).where(
            KnowledgeConceptLink.user_id == user_id,
            KnowledgeConceptLink.knowledge_node_id == to_node,
        )
        await self._db.execute(
            delete(KnowledgeConceptLink).where(
                KnowledgeConceptLink.user_id == user_id,
                KnowledgeConceptLink.knowledge_node_id == from_node,
                tuple_(KnowledgeConceptLink.source_type, KnowledgeConceptLink.source_id).in_(
                    existing_sources
                ),
            )
        )
        res = await self._db.execute(
            update(KnowledgeConceptLink)
            .where(
                KnowledgeConceptLink.user_id == user_id,
                KnowledgeConceptLink.knowledge_node_id == from_node,
            )
            .values(knowledge_node_id=to_node)
        )
        moved_links = int(res.rowcount or 0)
        existing_events = select(
            LearnerEvidence.source_type, LearnerEvidence.source_event_id
        ).where(LearnerEvidence.user_id == user_id, LearnerEvidence.knowledge_node_id == to_node)
        await self._db.execute(
            delete(LearnerEvidence).where(
                LearnerEvidence.user_id == user_id,
                LearnerEvidence.knowledge_node_id == from_node,
                tuple_(LearnerEvidence.source_type, LearnerEvidence.source_event_id).in_(
                    existing_events
                ),
            )
        )
        res = await self._db.execute(
            update(LearnerEvidence)
            .where(
                LearnerEvidence.user_id == user_id,
                LearnerEvidence.knowledge_node_id == from_node,
            )
            .values(knowledge_node_id=to_node)
        )
        moved_ev = int(res.rowcount or 0)
        return moved_links, moved_ev
