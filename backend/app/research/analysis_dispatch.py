"""Hands pending paper analyses to the Celery broker (same best-effort pattern as extraction: if the
broker is unreachable the analysis stays `pending` and the periodic dispatcher sends it later; a
duplicate send is harmless because the worker claims atomically)."""

from __future__ import annotations

import uuid

import structlog

from app.core.config import get_settings
from app.knowledge.dispatch import ExtractionDispatcher

logger = structlog.get_logger(__name__)

RUN_TASK = "research.run_paper_analysis"
DISPATCH_TASK = "research.dispatch_pending"
SWEEP_TASK = "research.sweep_stale_analyses"


class CeleryAnalysisDispatcher:
    def available(self) -> bool:
        return bool(get_settings().celery_broker_url)

    def dispatch(self, job_id: uuid.UUID) -> bool:
        if not self.available():
            return False
        from app.ingestion.worker import celery_app

        try:
            celery_app.send_task(RUN_TASK, args=[str(job_id)])
        except Exception as exc:  # broker down: the dispatcher will retry
            logger.warning("paper_analysis_dispatch_failed", error_type=type(exc).__name__)
            return False
        return True


def get_analysis_dispatcher() -> ExtractionDispatcher:
    return CeleryAnalysisDispatcher()
