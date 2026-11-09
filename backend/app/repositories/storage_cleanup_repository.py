import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage_cleanup import StorageCleanup


class StorageCleanupRepository:
    """SQL for the storage_cleanup outbox (D-66)."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def enqueue(self, keys: Sequence[str], reason: str) -> list[StorageCleanup]:
        """Add keys to delete. Call inside the transaction that deletes the document rows."""
        rows = [StorageCleanup(storage_key=k, reason=reason) for k in dict.fromkeys(keys)]
        self._db.add_all(rows)
        await self._db.flush()
        return rows

    async def claim_due(
        self, now: datetime, *, limit: int, max_attempts: int
    ) -> list[StorageCleanup]:
        """Lock a batch of pending rows. SKIP LOCKED lets several workers run without clashing."""
        stmt = (
            select(StorageCleanup)
            .where(
                StorageCleanup.done_at.is_(None),
                StorageCleanup.next_attempt_at <= now,
                StorageCleanup.attempts < max_attempts,
            )
            .order_by(StorageCleanup.next_attempt_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list((await self._db.execute(stmt)).scalars().all())

    async def mark_done(self, row_id: uuid.UUID, now: datetime, error_code: str | None) -> None:
        await self._db.execute(
            update(StorageCleanup)
            .where(StorageCleanup.id == row_id)
            .values(done_at=now, last_error_code=error_code)
        )

    async def mark_failed(
        self, row_id: uuid.UUID, error_code: str, next_attempt_at: datetime
    ) -> None:
        await self._db.execute(
            update(StorageCleanup)
            .where(StorageCleanup.id == row_id)
            .values(
                attempts=StorageCleanup.attempts + 1,
                last_error_code=error_code,
                next_attempt_at=next_attempt_at,
            )
        )

    async def count_exhausted(self, max_attempts: int) -> int:
        stmt = select(StorageCleanup.id).where(
            StorageCleanup.done_at.is_(None), StorageCleanup.attempts >= max_attempts
        )
        return len((await self._db.execute(stmt)).scalars().all())
