"""Hands queued jobs to the Celery broker. The API process uses this; it never runs parsers.

`dispatch` is best effort: when the broker is unreachable the job simply stays `queued` and the
periodic sweeper (`ingestion.dispatch_queued`) sends it later (D-68), so an upload is never lost.
"""

import uuid
from typing import Protocol

import structlog

from app.core.config import get_settings

logger = structlog.get_logger(__name__)

PROCESS_TASK = "ingestion.process_document"


class JobDispatcher(Protocol):
    def available(self) -> bool:
        """False when no broker is configured, so processing could never start."""

    def dispatch(self, job_id: uuid.UUID) -> bool:
        """Send the job to the worker. True when the broker accepted it."""


class CeleryDispatcher:
    def available(self) -> bool:
        return bool(get_settings().celery_broker_url)

    def dispatch(self, job_id: uuid.UUID) -> bool:
        if not self.available():
            return False
        from app.ingestion.worker import celery_app

        try:
            celery_app.send_task(PROCESS_TASK, args=[str(job_id)])
        except Exception as exc:  # broker down: the sweeper will retry
            logger.warning("job_dispatch_failed", error_type=type(exc).__name__)
            return False
        return True


def get_job_dispatcher() -> JobDispatcher:
    return CeleryDispatcher()
