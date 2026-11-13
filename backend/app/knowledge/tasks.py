"""Celery tasks for knowledge extraction. Thin: only a job id travels through the broker.

No automatic Celery retry: the run owns its limited provider retries, and a worker that dies
mid-run leaves the job to the stale-job sweeper, which FAILS it rather than restarting a billed
extraction (same rule as D-85). `acks_late` redelivery is harmless because the run claims the job
atomically."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from celery import Task

from app.ai.orchestration.runtime import AiRuntime, get_ai_runtime
from app.core.config import get_settings
from app.ingestion.db import task_session_factory
from app.ingestion.worker import celery_app
from app.knowledge import errors
from app.knowledge.dispatch import DISPATCH_TASK, RUN_TASK, SWEEP_TASK
from app.knowledge.extraction import ExtractionDeps, run_extraction
from app.repositories.knowledge_job_repository import KnowledgeJobRepository

logger = structlog.get_logger(__name__)
_settings = get_settings()


class KnowledgeTask(Task):
    abstract = True
    max_retries = 0  # never auto-restart an expensive extraction


@celery_app.task(
    name=RUN_TASK,
    base=KnowledgeTask,
    bind=True,
    soft_time_limit=_settings.knowledge_task_soft_time_limit_seconds,
    time_limit=_settings.knowledge_task_hard_time_limit_seconds,
)
def run_extraction_task(self: Task, job_id: str, runtime: AiRuntime | None = None) -> str:
    async def run() -> str:
        rt = runtime or get_ai_runtime()
        async with task_session_factory() as factory:
            return await run_extraction(
                ExtractionDeps(factory, rt), uuid.UUID(job_id), self.request.id
            )

    return asyncio.run(run())


@celery_app.task(name=DISPATCH_TASK, base=KnowledgeTask)
def dispatch_pending() -> dict[str, int]:
    """Send jobs that were committed but never delivered (broker was down, message lost)."""

    async def run() -> int:
        now = datetime.now(UTC)
        sent = 0
        async with task_session_factory() as factory, factory() as db:
            repo = KnowledgeJobRepository(db)
            for job_id in await repo.pending_older_than(now - timedelta(seconds=90), limit=100):
                celery_app.send_task(RUN_TASK, args=[str(job_id)])
                await repo.touch(job_id, now)
                sent += 1
            await db.commit()
        return sent

    return {"dispatched": asyncio.run(run())}


@celery_app.task(name=SWEEP_TASK, base=KnowledgeTask)
def sweep_stale_jobs() -> dict[str, Any]:
    """Fail jobs that started but stopped reporting (worker died). Never restarts them."""

    async def run() -> int:
        now = datetime.now(UTC)
        cutoff = now - timedelta(seconds=get_settings().knowledge_stale_job_seconds)
        async with task_session_factory() as factory, factory() as db:
            count = await KnowledgeJobRepository(db).fail_stale(cutoff, now, errors.INTERRUPTED)
            await db.commit()
        return count

    failed = asyncio.run(run())
    if failed:
        logger.warning("stale_extraction_jobs_failed", count=failed)
    return {"failed": failed}
