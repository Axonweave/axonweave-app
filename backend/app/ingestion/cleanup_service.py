"""Processes the storage_cleanup outbox (D-66): delete objects, then mark the rows done.

The database row is the source of truth. An object is only forgotten after the storage delete
succeeded; failures back off and are retried, and rows that keep failing are reported by count
(never by key) so someone can look. Deleting a missing object counts as success, so retries
are safe.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ingestion import errors
from app.repositories.storage_cleanup_repository import StorageCleanupRepository
from app.storage.base import StorageBackend, StorageError
from app.storage.keys import is_valid_original_key

logger = structlog.get_logger(__name__)

BATCH_SIZE = 50
MAX_ATTEMPTS = 10
_BASE_DELAY_SECONDS = 30
_MAX_DELAY_SECONDS = 6 * 3600


@dataclass(frozen=True)
class CleanupResult:
    deleted: int
    failed: int
    skipped_invalid: int
    exhausted: int


def _backoff(attempts: int) -> timedelta:
    return timedelta(seconds=min(_BASE_DELAY_SECONDS * (2**attempts), _MAX_DELAY_SECONDS))


async def process_outbox(
    session_factory: async_sessionmaker[AsyncSession],
    storage: StorageBackend,
    *,
    now: datetime | None = None,
    limit: int = BATCH_SIZE,
) -> CleanupResult:
    clock = now or datetime.now(UTC)
    deleted = failed = skipped = 0
    async with session_factory() as db:
        repo = StorageCleanupRepository(db)
        batch = await repo.claim_due(clock, limit=limit, max_attempts=MAX_ATTEMPTS)
        for row in batch:
            if not is_valid_original_key(row.storage_key):
                # Defence in depth: never act on a key this code could not have generated.
                await repo.mark_done(row.id, clock, errors.INVALID_STORAGE_KEY)
                skipped += 1
                continue
            try:
                await storage.delete(row.storage_key)
            except StorageError as exc:
                await repo.mark_failed(row.id, exc.code, clock + _backoff(row.attempts))
                failed += 1
            else:
                await repo.mark_done(row.id, clock, None)
                deleted += 1
        exhausted = await repo.count_exhausted(MAX_ATTEMPTS)
        await db.commit()
    if exhausted:
        logger.error("storage_cleanup_exhausted", count=exhausted)
    logger.info("storage_cleanup_run", deleted=deleted, failed=failed, skipped_invalid=skipped)
    return CleanupResult(deleted, failed, skipped, exhausted)
