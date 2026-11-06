"""Conversation persistence. Every query is scoped by the owning user (rule 3)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.message import Message
from app.models.user import User

_ACTIVE_GENERATION = ("pending", "streaming")


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class AiConversationRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(
        self, *, user_id: uuid.UUID, title: str | None, model_id: str | None
    ) -> Conversation:
        conv = Conversation(user_id=user_id, title=title, model_id=model_id, status="active")
        self._db.add(conv)
        await self._db.flush()
        return conv

    async def get_owned(
        self, *, conversation_id: uuid.UUID, user_id: uuid.UUID, for_update: bool = False
    ) -> Conversation | None:
        stmt = select(Conversation).where(
            Conversation.id == conversation_id, Conversation.user_id == user_id
        )
        if for_update:
            stmt = stmt.with_for_update()
        return (await self._db.execute(stmt)).scalar_one_or_none()

    async def list_owned(
        self,
        *,
        user_id: uuid.UUID,
        status: str | None,
        q: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Conversation], int]:
        conditions = [Conversation.user_id == user_id]
        if status:
            conditions.append(Conversation.status == status)
        if q:
            conditions.append(Conversation.title.ilike(f"%{_escape_like(q)}%", escape="\\"))
        activity = func.coalesce(Conversation.last_message_at, Conversation.created_at)
        total = (
            await self._db.execute(select(func.count(Conversation.id)).where(*conditions))
        ).scalar_one()
        rows = (
            await self._db.execute(
                select(Conversation)
                .where(*conditions)
                .order_by(activity.desc(), Conversation.id.desc())
                .limit(limit)
                .offset(offset)
            )
        ).scalars()
        return list(rows), total

    async def delete_owned(self, *, conversation_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        result = await self._db.execute(
            delete(Conversation).where(
                Conversation.id == conversation_id, Conversation.user_id == user_id
            )
        )
        return bool(getattr(result, "rowcount", 0))

    async def touch(self, conversation: Conversation) -> None:
        conversation.last_message_at = datetime.now(UTC)
        await self._db.flush()

    # generation guards ───────────────────────────────────────────────────────

    async def lock_user(self, user_id: uuid.UUID) -> None:
        """Serialise per-user cap checks: two concurrent sends cannot both pass (D-43)."""
        await self._db.execute(select(User.id).where(User.id == user_id).with_for_update())

    async def count_active_generations(self, user_id: uuid.UUID) -> int:
        return (
            await self._db.execute(
                select(func.count(Message.id)).where(
                    Message.user_id == user_id,
                    Message.role == "assistant",
                    Message.status.in_(_ACTIVE_GENERATION),
                )
            )
        ).scalar_one()
