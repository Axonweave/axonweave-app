"""Celery tasks for paper analysis. Thin: only an analysis id travels through the broker.

No automatic retry: a worker that dies mid-run leaves the analysis to the stale sweeper, which
FAILS it rather than restarting a billed run (same rule as D-85)."""

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
from app.knowledge.extraction import ExtractionDeps
from app.repositories.research_analysis_repository import ResearchAnalysisRepository
from app.research import errors
from app.research.analysis_dispatch import DISPATCH_TASK, RUN_TASK, SWEEP_TASK
from app.research.analysis_run import run_paper_analysis

logger = structlog.get_logger(__name__)
_settings = get_settings()


class AnalysisTask(Task):
    abstract = True
    max_retries = 0  # never auto-restart an expensive analysis


@celery_app.task(
    name=RUN_TASK,
    base=AnalysisTask,
    bind=True,
    soft_time_limit=_settings.knowledge_task_soft_time_limit_seconds,
    time_limit=_settings.knowledge_task_hard_time_limit_seconds,
)
def run_paper_analysis_task(
    self: Task, extraction_id: str, runtime: AiRuntime | None = None
) -> str:
    async def run() -> str:
        rt = runtime or get_ai_runtime()
        async with task_session_factory() as factory:
            return await run_paper_analysis(
                ExtractionDeps(factory, rt), uuid.UUID(extraction_id), self.request.id
            )

    return asyncio.run(run())


@celery_app.task(name=DISPATCH_TASK, base=AnalysisTask)
def dispatch_pending_analyses() -> dict[str, int]:
    """Send analyses that were committed but never delivered (broker was down, message lost)."""

    async def run() -> int:
        now = datetime.now(UTC)
        sent = 0
        async with task_session_factory() as factory, factory() as db:
            repo = ResearchAnalysisRepository(db)
            for item in await repo.pending_older_than(now - timedelta(seconds=90), limit=100):
                celery_app.send_task(RUN_TASK, args=[str(item)])
                await repo.touch(item, now)
                sent += 1
            await db.commit()
        return sent

    return {"dispatched": asyncio.run(run())}


@celery_app.task(name=SWEEP_TASK, base=AnalysisTask)
def sweep_stale_analyses() -> dict[str, Any]:
    """Fail analyses that started but stopped reporting (worker died). Never restarts them."""

    async def run() -> int:
        now = datetime.now(UTC)
        cutoff = now - timedelta(seconds=get_settings().knowledge_stale_job_seconds)
        async with task_session_factory() as factory, factory() as db:
            repo = ResearchAnalysisRepository(db)
            count = await repo.fail_stale(cutoff, now, errors.INTERRUPTED)
            await repo.refresh_stuck_paper_statuses()
            await db.commit()
        return count

    failed = asyncio.run(run())
    if failed:
        logger.warning("stale_paper_analyses_failed", count=failed)
    return {"failed": failed}
