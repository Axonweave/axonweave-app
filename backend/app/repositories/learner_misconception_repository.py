"""Persistence for misconceptions (Milestone 6.7). Every query is filtered by `user_id`. Wrong
answers are read from the owner's quiz data only; their text is never copied into these tables."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeEdge, KnowledgeNode
from app.models.learner import (
    LearnerEvidence,
    LearnerMisconception,
    LearnerMisconceptionEvidence,
)
from app.models.quiz import QuizAttemptAnswer, QuizQuestion


class LearnerMisconceptionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # evidence the detector may use ───────────────────────────────────────────

    async def uncorrected_wrong_answers(
        self, user_id: uuid.UUID, node_id: uuid.UUID, limit: int
    ) -> list[tuple[QuizAttemptAnswer, QuizQuestion]]:
        """Newest wrong, actually attempted, graded answers on this concept whose question has
        NOT been answered correctly since (a corrected error is a slip, not a misconception)."""
        later_right = QuizAttemptAnswer.__table__.alias("later")
        fixed = (
            select(later_right.c.id)
            .where(
                later_right.c.user_id == user_id,
                later_right.c.question_id == QuizAttemptAnswer.question_id,
                later_right.c.is_correct.is_(True),
                later_right.c.submitted_at > QuizAttemptAnswer.submitted_at,
            )
            .exists()
        )
        rows = await self._db.execute(
            select(QuizAttemptAnswer, QuizQuestion)
            .join(
                LearnerEvidence,
                and_(
                    LearnerEvidence.source_event_id == QuizAttemptAnswer.id,
                    LearnerEvidence.user_id == QuizAttemptAnswer.user_id,
                ),
            )
            .join(QuizQuestion, QuizQuestion.id == QuizAttemptAnswer.question_id)
            .where(
                LearnerEvidence.user_id == user_id,
                LearnerEvidence.knowledge_node_id == node_id,
                LearnerEvidence.source_type == "quiz_answer",
                QuizAttemptAnswer.evaluation_status == "graded",
                QuizAttemptAnswer.is_correct.is_(False),
                ~fixed,
            )
            .order_by(QuizAttemptAnswer.submitted_at.desc(), QuizAttemptAnswer.id)
            .limit(limit * 4)
        )
        # blank, skipped or empty answers are gaps, not misunderstandings
        attempted = [(a, q) for a, q in rows.all() if a.submitted_answer not in (None, "", [], {})]
        return attempted[:limit]

    async def neighbours(
        self, user_id: uuid.UUID, node_id: uuid.UUID, limit: int
    ) -> list[KnowledgeNode]:
        ids = await self._db.execute(
            select(KnowledgeEdge.source_node_id, KnowledgeEdge.target_node_id)
            .where(
                KnowledgeEdge.user_id == user_id,
                or_(
                    KnowledgeEdge.source_node_id == node_id, KnowledgeEdge.target_node_id == node_id
                ),
            )
            .limit(limit * 2)
        )
        other: list[uuid.UUID] = []
        for s, t in ids.all():
            n = t if s == node_id else s
            if n not in other:
                other.append(n)
        if not other:
            return []
        rows = await self._db.execute(
            select(KnowledgeNode).where(
                KnowledgeNode.user_id == user_id,
                KnowledgeNode.id.in_(other[:limit]),
                KnowledgeNode.archived_at.is_(None),
            )
        )
        return list(rows.scalars())

    # misconceptions ──────────────────────────────────────────────────────────

    async def by_fingerprint(
        self, user_id: uuid.UUID, node_id: uuid.UUID, fingerprint: str
    ) -> list[LearnerMisconception]:
        rows = await self._db.execute(
            select(LearnerMisconception).where(
                LearnerMisconception.user_id == user_id,
                LearnerMisconception.knowledge_node_id == node_id,
                LearnerMisconception.fingerprint == fingerprint,
            )
        )
        return list(rows.scalars())

    async def insert(self, fields: dict[str, Any]) -> uuid.UUID | None:
        """None when the same misconception (same description) already exists for the concept,
        including a dismissed one, which must stay dismissed."""
        result = await self._db.execute(
            pg_insert(LearnerMisconception)
            .values(id=uuid.uuid4(), **fields)
            .on_conflict_do_nothing(constraint="uq_misconceptions_key")
            .returning(LearnerMisconception.id)
        )
        row = result.first()
        return None if row is None else row[0]

    async def add_evidence(
        self,
        user_id: uuid.UUID,
        misconception_id: uuid.UUID,
        items: Sequence[tuple[uuid.UUID, uuid.UUID]],
    ) -> None:
        for event_id, question_id in items:
            await self._db.execute(
                pg_insert(LearnerMisconceptionEvidence)
                .values(
                    id=uuid.uuid4(),
                    user_id=user_id,
                    misconception_id=misconception_id,
                    source_type="quiz_answer",
                    source_event_id=event_id,
                    source_id=question_id,
                )
                .on_conflict_do_nothing()
            )

    async def get(self, user_id: uuid.UUID, mid: uuid.UUID) -> LearnerMisconception | None:
        return (
            await self._db.execute(
                select(LearnerMisconception).where(
                    LearnerMisconception.id == mid, LearnerMisconception.user_id == user_id
                )
            )
        ).scalar_one_or_none()

    async def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        node_id: uuid.UUID | None,
        workspace_id: uuid.UUID | None,
        status: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[tuple[LearnerMisconception, str]], int]:
        conds = [LearnerMisconception.user_id == user_id]
        if node_id:
            conds.append(LearnerMisconception.knowledge_node_id == node_id)
        if workspace_id:
            conds.append(LearnerMisconception.workspace_id == workspace_id)
        if status:
            conds.append(LearnerMisconception.status == status)
        total = (
            await self._db.execute(
                select(func.count()).select_from(LearnerMisconception).where(*conds)
            )
        ).scalar_one()
        rows = await self._db.execute(
            select(LearnerMisconception, KnowledgeNode.name)
            .join(KnowledgeNode, KnowledgeNode.id == LearnerMisconception.knowledge_node_id)
            .where(*conds)
            .order_by(LearnerMisconception.confidence.desc(), LearnerMisconception.id)
            .limit(limit)
            .offset(offset)
        )
        return [(m, n) for m, n in rows.all()], int(total)  # noqa: C416

    async def node_names(
        self, user_id: uuid.UUID, ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, str]:
        if not ids:
            return {}
        rows = await self._db.execute(
            select(KnowledgeNode.id, KnowledgeNode.name).where(
                KnowledgeNode.user_id == user_id, KnowledgeNode.id.in_(ids)
            )
        )
        return {i: n for i, n in rows.all()}  # noqa: C416

    async def evidence_details(
        self, user_id: uuid.UUID, mid: uuid.UUID
    ) -> list[tuple[QuizAttemptAnswer, QuizQuestion]]:
        rows = await self._db.execute(
            select(QuizAttemptAnswer, QuizQuestion)
            .join(
                LearnerMisconceptionEvidence,
                and_(
                    LearnerMisconceptionEvidence.source_event_id == QuizAttemptAnswer.id,
                    LearnerMisconceptionEvidence.user_id == QuizAttemptAnswer.user_id,
                ),
            )
            .join(QuizQuestion, QuizQuestion.id == QuizAttemptAnswer.question_id)
            .where(
                LearnerMisconceptionEvidence.user_id == user_id,
                LearnerMisconceptionEvidence.misconception_id == mid,
            )
            .order_by(QuizAttemptAnswer.submitted_at.desc())
        )
        return [(a, q) for a, q in rows.all()]  # noqa: C416

    async def set_status(
        self, row: LearnerMisconception, status: str, now: datetime | None
    ) -> None:
        row.status = status
        row.dismissed_at = now if status == "dismissed" else None
        await self._db.flush()
