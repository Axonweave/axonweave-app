"""Celery tasks. Thin: they open a session and call a service function.

Task arguments never carry document content, only ids. Failures are recorded as safe codes.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from celery import Task

from app.core.config import get_settings
from app.ingestion import errors
from app.ingestion.cleanup_service import process_outbox
from app.ingestion.db import task_session_factory
from app.ingestion.worker import celery_app
from app.repositories.processing_job_repository import ProcessingJobRepository
from app.storage.factory import get_storage_backend

logger = structlog.get_logger(__name__)


class SafeTask(Task):
    """Base class for Axonweave tasks.

    - Transient failures (`TransientTaskError`) are retried with exponential backoff and jitter, up
      to CELERY_MAX_RETRIES; anything else is not retried automatically.
    - Soft/hard time limits come from the app config (see worker.py).
    - Failures are logged with a safe code only (worker.py signal handler): no args, no message.
    """

    abstract = True
    autoretry_for = (errors.TransientTaskError,)
    retry_backoff = True
    retry_backoff_max = 600
    retry_jitter = True
    max_retries = get_settings().celery_max_retries


@celery_app.task(name="system.ping", base=SafeTask)
def ping() -> dict[str, str]:
    """Health task: proves a worker picked a task up and can run code."""
    return {"status": "ok"}


@celery_app.task(name="storage.process_cleanup_outbox", base=SafeTask)
def process_cleanup_outbox() -> dict[str, int]:
    async def run() -> dict[str, int]:
        storage = get_storage_backend()
        async with task_session_factory() as factory:
            result = await process_outbox(factory, storage)
        return {
            "deleted": result.deleted,
            "failed": result.failed,
            "skipped_invalid": result.skipped_invalid,
            "exhausted": result.exhausted,
        }

    return asyncio.run(run())


@celery_app.task(name="ingestion.sweep_stale_jobs", base=SafeTask)
def sweep_stale_jobs() -> dict[str, Any]:
    """Fail jobs stuck in `running` past twice the hard time limit (worker died mid-job)."""

    async def run() -> int:
        settings = get_settings()
        now = datetime.now(UTC)
        cutoff = now - timedelta(seconds=2 * settings.celery_task_hard_time_limit_seconds)
        async with task_session_factory() as factory, factory() as db:
            count = await ProcessingJobRepository(db).fail_stale_running(
                cutoff, now, errors.WORKER_LOST
            )
            await db.commit()
        return count

    failed = asyncio.run(run())
    if failed:
        logger.warning("stale_jobs_failed", count=failed)
    return {"failed": failed}
