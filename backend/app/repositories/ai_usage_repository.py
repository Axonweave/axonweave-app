"""Usage records and the daily counters behind quotas. Scoped by user (rule 3)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_usage_record import AiUsageRecord
from app.models.message import Message


def utc_day_start() -> datetime:
    return datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


class AiUsageRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def add(self, **fields: Any) -> AiUsageRecord:
        record = AiUsageRecord(**fields)
        self._db.add(record)
        await self._db.flush()
        return record

    async def messages_today(self, user_id: uuid.UUID) -> int:
        """User-authored messages since 00:00 UTC (the daily message quota)."""
        return (
            await self._db.execute(
                select(func.count(Message.id)).where(
                    Message.user_id == user_id,
                    Message.role == "user",
                    Message.created_at >= utc_day_start(),
                )
            )
        ).scalar_one()

    async def tokens_today(self, user_id: uuid.UUID) -> int:
        """Reported tokens since 00:00 UTC. Unknown (NULL) counts add nothing."""
        total = (
            await self._db.execute(
                select(
                    func.coalesce(func.sum(AiUsageRecord.input_tokens), 0)
                    + func.coalesce(func.sum(AiUsageRecord.output_tokens), 0)
                ).where(
                    AiUsageRecord.user_id == user_id,
                    AiUsageRecord.created_at >= utc_day_start(),
                )
            )
        ).scalar_one()
        return int(total or 0)
