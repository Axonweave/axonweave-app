"""Usage records and the counters behind quotas and the usage endpoints.

Everything is scoped by the owning user (rule 3). Unknown token counts and costs are NULL in the
database and stay unknown here: sums skip NULLs and are reported next to how many rows had a value.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_usage_record import AiUsageRecord
from app.models.llm_provider import LLMModel


def utc_day_start() -> datetime:
    return datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


@dataclass(frozen=True)
class UsageAggregate:
    """One row of the grouped usage query: a model and a currency."""

    model_internal_id: str
    model_display_name: str
    currency: str | None
    requests: int
    failed: int
    cancelled: int
    input_tokens: int
    output_tokens: int
    token_known_requests: int
    cost: Decimal
    cost_known_requests: int


class AiUsageRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def add(self, **fields: Any) -> AiUsageRecord:
        record = AiUsageRecord(**fields)
        self._db.add(record)
        await self._db.flush()
        return record

    # quotas ──────────────────────────────────────────────────────────────────

    async def requests_today(self, user_id: uuid.UUID) -> int:
        """Provider requests since 00:00 UTC, whatever their outcome and however they started
        (a new message or a regenerate), for the daily request quota."""
        return (
            await self._db.execute(
                select(func.count(AiUsageRecord.id)).where(
                    AiUsageRecord.user_id == user_id,
                    AiUsageRecord.created_at >= utc_day_start(),
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

    # usage endpoints ─────────────────────────────────────────────────────────

    async def list_for_user(
        self, *, user_id: uuid.UUID, status: str | None, since: datetime, limit: int, offset: int
    ) -> tuple[list[tuple[AiUsageRecord, str, str]], int]:
        conditions = [AiUsageRecord.user_id == user_id, AiUsageRecord.created_at >= since]
        if status:
            conditions.append(AiUsageRecord.request_status == status)
        total = (
            await self._db.execute(select(func.count(AiUsageRecord.id)).where(*conditions))
        ).scalar_one()
        rows = (
            await self._db.execute(
                select(AiUsageRecord, LLMModel.internal_id, LLMModel.display_name)
                .join(LLMModel, LLMModel.id == AiUsageRecord.model_id)
                .where(*conditions)
                .order_by(AiUsageRecord.created_at.desc(), AiUsageRecord.id.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
        return [(r[0], r[1], r[2]) for r in rows], total

    async def aggregate(self, *, user_id: uuid.UUID, since: datetime) -> list[UsageAggregate]:
        """Grouped by model and currency so costs in different currencies are never added."""
        record = AiUsageRecord
        stmt = (
            select(
                LLMModel.internal_id,
                LLMModel.display_name,
                record.currency,
                func.count(record.id),
                func.count(record.id).filter(record.request_status == "failed"),
                func.count(record.id).filter(record.request_status == "cancelled"),
                func.coalesce(func.sum(record.input_tokens), 0),
                func.coalesce(func.sum(record.output_tokens), 0),
                func.count(record.id).filter(
                    record.input_tokens.is_not(None) | record.output_tokens.is_not(None)
                ),
                func.coalesce(func.sum(record.estimated_cost), 0),
                func.count(record.estimated_cost),
            )
            .join(LLMModel, LLMModel.id == record.model_id)
            .where(record.user_id == user_id, record.created_at >= since)
            .group_by(LLMModel.internal_id, LLMModel.display_name, record.currency)
            .order_by(LLMModel.internal_id)
        )
        return [
            UsageAggregate(
                model_internal_id=r[0],
                model_display_name=r[1],
                currency=r[2],
                requests=int(r[3]),
                failed=int(r[4]),
                cancelled=int(r[5]),
                input_tokens=int(r[6]),
                output_tokens=int(r[7]),
                token_known_requests=int(r[8]),
                cost=Decimal(r[9]),
                cost_known_requests=int(r[10]),
            )
            for r in (await self._db.execute(stmt)).all()
        ]
