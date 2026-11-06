"""Message and feedback persistence. Every query is scoped by the owning user (rule 3)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message, MessageFeedback


class AiMessageRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def next_sequence(self, *, conversation_id: uuid.UUID, user_id: uuid.UUID) -> int:
        """Call only while holding the conversation row lock (D-42)."""
        current = (
            await self._db.execute(
                select(func.coalesce(func.max(Message.sequence_number), 0)).where(
                    Message.conversation_id == conversation_id, Message.user_id == user_id
                )
            )
        ).scalar_one()
        return int(current) + 1

    async def add(self, **fields: Any) -> Message:
        message = Message(**fields)
        self._db.add(message)
        await self._db.flush()
        return message

    async def list_for_conversation(
        self, *, conversation_id: uuid.UUID, user_id: uuid.UUID, limit: int, offset: int
    ) -> tuple[list[Message], int]:
        cond = (Message.conversation_id == conversation_id, Message.user_id == user_id)
        total = (await self._db.execute(select(func.count(Message.id)).where(*cond))).scalar_one()
        rows = (
            await self._db.execute(
                select(Message)
                .where(*cond)
                .order_by(Message.sequence_number.asc())
                .limit(limit)
                .offset(offset)
            )
        ).scalars()
        return list(rows), total

    async def history(
        self, *, conversation_id: uuid.UUID, user_id: uuid.UUID, before_sequence: int
    ) -> list[Message]:
        """Completed, non-superseded messages before `before_sequence`, oldest first (D-47)."""
        rows = (
            await self._db.execute(
                select(Message)
                .where(
                    Message.conversation_id == conversation_id,
                    Message.user_id == user_id,
                    Message.sequence_number < before_sequence,
                    Message.superseded_at.is_(None),
                    Message.status == "completed",
                )
                .order_by(Message.sequence_number.asc())
            )
        ).scalars()
        return list(rows)

    async def get_owned(self, *, message_id: uuid.UUID, user_id: uuid.UUID) -> Message | None:
        return (
            await self._db.execute(
                select(Message).where(Message.id == message_id, Message.user_id == user_id)
            )
        ).scalar_one_or_none()

    async def message_count(self, *, conversation_id: uuid.UUID, user_id: uuid.UUID) -> int:
        return (
            await self._db.execute(
                select(func.count(Message.id)).where(
                    Message.conversation_id == conversation_id, Message.user_id == user_id
                )
            )
        ).scalar_one()

    # feedback ────────────────────────────────────────────────────────────────

    async def upsert_feedback(
        self, *, message_id: uuid.UUID, user_id: uuid.UUID, rating: str, text: str | None
    ) -> MessageFeedback:
        row = (
            await self._db.execute(
                select(MessageFeedback).where(
                    MessageFeedback.message_id == message_id, MessageFeedback.user_id == user_id
                )
            )
        ).scalar_one_or_none()
        if row is None:
            row = MessageFeedback(
                message_id=message_id, user_id=user_id, rating=rating, feedback_text=text
            )
            self._db.add(row)
        else:
            row.rating = rating
            row.feedback_text = text
        await self._db.flush()
        return row
