"""Hands pending generation jobs to the Celery broker. The API uses this; it never runs generation.

Dispatch is best effort: if the broker is unreachable the job simply stays `pending` and the
periodic sweeper (`study.dispatch_pending`) sends it later, so a request is never lost. Sending a
job twice is harmless: the worker claims it atomically (D-88).
"""

from __future__ import annotations

import uuid
from typing import Protocol

import structlog

from app.core.config import get_settings

logger = structlog.get_logger(__name__)

RUN_TASK = "study.run_generation"


class GenerationDispatcher(Protocol):
    def available(self) -> bool:
        """False when no broker is configured, so generation could never start."""

    def dispatch(self, job_id: uuid.UUID) -> bool:
        """Send the job to the worker. True when the broker accepted it."""


class CeleryGenerationDispatcher:
    def available(self) -> bool:
        return bool(get_settings().celery_broker_url)

    def dispatch(self, job_id: uuid.UUID) -> bool:
        if not self.available():
            return False
        from app.ingestion.worker import celery_app

        try:
            celery_app.send_task(RUN_TASK, args=[str(job_id)])
        except Exception as exc:  # broker down: the sweeper will retry
            logger.warning("generation_dispatch_failed", error_type=type(exc).__name__)
            return False
        return True


def get_generation_dispatcher() -> GenerationDispatcher:
    return CeleryGenerationDispatcher()
