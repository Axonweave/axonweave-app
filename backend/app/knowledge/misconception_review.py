"""What the learner can do with a detected misconception: confirm, dismiss, or correct the wording
(spec 15.3). Needs no model, only the owner's own rows."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.errors import KnowledgeError
from app.knowledge.misconceptions import (
    MisconceptionNotFoundError,
    clean_text,
    description_key,
)
from app.models.learner import LearnerMisconception
from app.repositories.learner_misconception_repository import LearnerMisconceptionRepository


class MisconceptionConflictError(KnowledgeError):
    code = "MISCONCEPTION_EXISTS"
    http_status = 409
    user_message = "Another misconception on this concept already has that description."


class MisconceptionReview:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._repo = LearnerMisconceptionRepository(db)

    async def get(self, user_id: uuid.UUID, mid: uuid.UUID) -> LearnerMisconception:
        row = await self._repo.get(user_id, mid)
        if row is None:
            raise MisconceptionNotFoundError()
        return row

    async def decide(self, user_id: uuid.UUID, mid: uuid.UUID, status: str) -> LearnerMisconception:
        row = await self.get(user_id, mid)
        await self._repo.set_status(row, status, datetime.now(UTC))
        await self._db.commit()
        await self._db.refresh(row)
        return row

    async def correct(
        self,
        user_id: uuid.UUID,
        mid: uuid.UUID,
        description: str | None,
        explanation: str | None,
        recommended_action: str | None,
    ) -> LearnerMisconception:
        row = await self.get(user_id, mid)
        if description is not None:
            row.description = clean_text(description, 300)
            row.description_key = description_key(row.description)
        if explanation is not None:
            row.explanation = clean_text(explanation, 900)
        if recommended_action is not None:
            row.recommended_action = clean_text(recommended_action, 300) or None
        row.status = "corrected"
        row.edited_by_user = True
        row.dismissed_at = None
        try:
            await self._db.commit()
        except IntegrityError:
            await self._db.rollback()
            raise MisconceptionConflictError() from None
        await self._db.refresh(row)
        return row
