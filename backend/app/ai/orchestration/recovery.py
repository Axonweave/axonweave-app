"""Recovery of stuck generations (D-46).

A crash, a restart or a lost task can leave an assistant message in `pending`/`streaming` forever,
which would also keep the one-active-generation index occupied. The sweeper marks such rows `failed`
and writes a failed usage row, so nothing stays active and nothing looks successful.

It never touches a generation this process is still running (the registry) and uses a
compare-and-set, so a generation that is merely slow is safe. Rows owned by ANOTHER process that is
alive are protected only by the staleness window (D-45: single-instance limit).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.orchestration.streaming import GenerationRegistry, get_generation_registry
from app.core.config import Settings
from app.core.logging import get_logger
from app.repositories.ai_catalog_repository import AiCatalogRepository
from app.repositories.ai_message_repository import AiMessageRepository
from app.repositories.ai_usage_repository import AiUsageRepository

logger = get_logger(__name__)

SWEEP_INTERVAL_SECONDS = 60.0
STALE_ERROR_CODE = "LLM_UNAVAILABLE"


async def sweep_stale_generations(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    registry: GenerationRegistry | None = None,
) -> int:
    """Mark stale active generations failed. Returns how many were recovered."""
    registry = registry or get_generation_registry()
    cutoff = datetime.now(UTC) - timedelta(seconds=settings.ai_stale_generation_seconds)
    recovered = 0
    async with session_factory() as db:
        messages = AiMessageRepository(db)
        catalog = AiCatalogRepository(db)
        usage = AiUsageRepository(db)
        for row in await messages.stale_generations(cutoff=cutoff, exclude=registry.active_ids()):
            if not await messages.fail_if_still_stale(message_id=row.id, cutoff=cutoff):
                continue
            model = await catalog.get_model(row.model_id) if row.model_id else None
            if model is not None:
                await usage.add(
                    user_id=row.user_id,
                    conversation_id=row.conversation_id,
                    message_id=row.id,
                    provider_id=model.provider_id,
                    model_id=model.id,
                    usage_source="unavailable",
                    request_status="failed",
                    error_code=STALE_ERROR_CODE,
                )
            await db.commit()
            recovered += 1
            logger.warning("ai_stale_generation_recovered", message_id=str(row.id))
    return recovered


async def run_sweeper(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    interval: float = SWEEP_INTERVAL_SECONDS,
) -> None:
    """Sweep at startup and then periodically, until cancelled at shutdown."""
    while True:
        try:
            await sweep_stale_generations(session_factory, settings)
        except asyncio.CancelledError:
            raise
        except DBAPIError:
            logger.warning("ai_sweep_skipped", reason="database_not_ready")
        except Exception:  # the sweeper must never die and must never take the app down
            logger.exception("ai_sweep_failed")
        await asyncio.sleep(interval)
