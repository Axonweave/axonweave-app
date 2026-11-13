"""Hands pending extraction jobs to the Celery broker. The API uses this; it never runs extraction.

Best effort: if the broker is unreachable the job stays `pending` and the periodic dispatcher sends
it later, so a request is never lost. Sending a job twice is harmless: the worker claims it
atomically (same pattern as study generation, D-85)."""

from __future__ import annotations

import uuid
from typing import Protocol

import structlog

from app.core.config import get_settings

logger = structlog.get_logger(__name__)

RUN_TASK = "knowledge.run_extraction"
DISPATCH_TASK = "knowledge.dispatch_pending"
SWEEP_TASK = "knowledge.sweep_stale_jobs"
RECALC_TASK = "knowledge.recalculate_mastery"


class ExtractionDispatcher(Protocol):
    def available(self) -> bool:
        """False when no broker is configured, so extraction could never start."""

    def dispatch(self, job_id: uuid.UUID) -> bool:
        """Send the job to the worker. True when the broker accepted it."""


class CeleryExtractionDispatcher:
    def available(self) -> bool:
        return bool(get_settings().celery_broker_url)

    def dispatch(self, job_id: uuid.UUID) -> bool:
        if not self.available():
            return False
        from app.ingestion.worker import celery_app

        try:
            celery_app.send_task(RUN_TASK, args=[str(job_id)])
        except Exception as exc:  # broker down: the dispatcher will retry
            logger.warning("extraction_dispatch_failed", error_type=type(exc).__name__)
            return False
        return True


def get_extraction_dispatcher() -> ExtractionDispatcher:
    return CeleryExtractionDispatcher()
