"""Celery tasks for study generation. Thin: only a job id travels through the broker.

No automatic Celery retry: the engine owns its (limited) provider retries, and a worker that dies
mid-run leaves the job to the stale-job sweeper, which FAILS it rather than restarting an expensive
generation whose outcome is unknown (D-88). `acks_late` redelivery is harmless because the engine
claims the job atomically.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from celery import Task

from app.ai.orchestration.runtime import AiRuntime, get_ai_runtime
from app.core.config import get_settings
from app.embeddings.registry import (
    close_embedding_providers,
    embedding_configured,
    get_embedding_provider,
)
from app.embeddings.service import EmbeddingService
from app.ingestion.db import task_session_factory
from app.ingestion.worker import celery_app
from app.repositories.generation_job_repository import GenerationJobRepository
from app.repositories.study_export_repository import StudyExportRepository
from app.storage.factory import get_storage_backend
from app.study import errors
from app.study.dispatch import EXPORT_TASK, RUN_TASK
from app.study.engine import EngineDeps, run_generation
from app.study.export_runner import expire_exports, run_export

logger = structlog.get_logger(__name__)
_settings = get_settings()


class StudyTask(Task):
    abstract = True
    max_retries = 0  # never auto-restart an expensive generation


@celery_app.task(
    name=RUN_TASK,
    base=StudyTask,
    bind=True,
    soft_time_limit=_settings.study_task_soft_time_limit_seconds,
    time_limit=_settings.study_task_hard_time_limit_seconds,
)
def run_generation_task(self: Task, job_id: str, runtime: AiRuntime | None = None) -> str:
    async def run() -> str:
        settings = get_settings()
        rt = runtime or get_ai_runtime()
        async with task_session_factory() as factory:
            embedder = (
                EmbeddingService(factory, get_embedding_provider(settings), settings)
                if embedding_configured(settings)
                else None
            )
            try:
                return await run_generation(
                    EngineDeps(factory, rt, embedder), uuid.UUID(job_id), self.request.id
                )
            finally:
                await close_embedding_providers()

    return asyncio.run(run())


@celery_app.task(name="study.dispatch_pending", base=StudyTask)
def dispatch_pending() -> dict[str, int]:
    """Send jobs that were committed but never delivered (broker was down, message lost)."""

    async def run() -> int:
        now = datetime.now(UTC)
        sent = 0
        async with task_session_factory() as factory, factory() as db:
            repo = GenerationJobRepository(db)
            for job_id in await repo.pending_older_than(now - timedelta(seconds=90), limit=100):
                celery_app.send_task(RUN_TASK, args=[str(job_id)])
                await repo.touch(job_id, now)
                sent += 1
            await db.commit()
        return sent

    return {"dispatched": asyncio.run(run())}


@celery_app.task(name="study.sweep_stale_jobs", base=StudyTask)
def sweep_stale_jobs() -> dict[str, Any]:
    """Fail jobs that started but stopped reporting (worker died). Never restarts them."""

    async def run() -> int:
        now = datetime.now(UTC)
        cutoff = now - timedelta(seconds=get_settings().study_stale_job_seconds)
        async with task_session_factory() as factory, factory() as db:
            count = await GenerationJobRepository(db).fail_stale(cutoff, now, errors.INTERRUPTED)
            await db.commit()
        return count

    failed = asyncio.run(run())
    if failed:
        logger.warning("stale_generation_jobs_failed", count=failed)
    return {"failed": failed}


@celery_app.task(name=EXPORT_TASK, base=StudyTask, bind=True, soft_time_limit=120, time_limit=150)
def run_export_task(self: Task, export_id: str) -> str:
    async def run() -> str:
        settings = get_settings()
        async with task_session_factory() as factory:
            return await run_export(factory, get_storage_backend(), settings, uuid.UUID(export_id))

    return asyncio.run(run())


@celery_app.task(name="study.sweep_exports", base=StudyTask)
def sweep_exports() -> dict[str, int]:
    """Resend exports that were never delivered to a worker, and delete expired export files."""

    async def run() -> tuple[int, int]:
        now = datetime.now(UTC)
        sent = 0
        async with task_session_factory() as factory:
            async with factory() as db:
                for export_id in await StudyExportRepository(db).pending_older_than(
                    now - timedelta(seconds=90), limit=100
                ):
                    celery_app.send_task(EXPORT_TASK, args=[str(export_id)])
                    sent += 1
            expired = await expire_exports(factory, get_storage_backend(), now)
        return sent, expired

    sent, expired = asyncio.run(run())
    return {"dispatched": sent, "expired": expired}
