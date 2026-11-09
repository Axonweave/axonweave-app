"""Celery application (Phase 3, D-63).

Importing this module is safe without Redis: the API imports it only to enqueue tasks. With no
CELERY_BROKER_URL configured the broker is the in-memory transport, so nothing is delivered and the
document endpoints (M2) answer 503 `PROCESSING_UNAVAILABLE` instead.

Running tasks eagerly in tests: see `docs/AI_TESTING.md` ("Celery in tests") and
`tests/conftest.py::celery_eager`.
"""

from typing import Any

import structlog
from celery import Celery
from celery.signals import task_failure, worker_process_init

from app.core.config import Settings, get_settings
from app.ingestion.errors import safe_error_code

logger = structlog.get_logger(__name__)

# Beat schedule skeleton: (task name, seconds). Real work arrives with the stages in M2/M3.
BEAT_SCHEDULE: dict[str, dict[str, Any]] = {
    "storage-cleanup-outbox": {
        "task": "storage.process_cleanup_outbox",
        "schedule": 60.0,
    },
    "dispatch-queued-processing-jobs": {
        "task": "ingestion.dispatch_queued",
        "schedule": 60.0,
    },
    "sweep-stale-processing-jobs": {
        "task": "ingestion.sweep_stale_jobs",
        "schedule": 120.0,
    },
}


def create_celery_app(settings: Settings | None = None) -> Celery:
    cfg = settings or get_settings()
    app = Celery(
        "axonweave",
        broker=cfg.celery_broker_url or "memory://",
        backend=cfg.celery_result_backend or None,
        include=["app.ingestion.tasks"],
    )
    app.conf.update(
        # Celery itself also reads CELERY_BROKER_URL from the environment and lets it win; our
        # Settings read the same variable, so the two always agree.
        broker_url=cfg.celery_broker_url or "memory://",
        result_backend=cfg.celery_result_backend or None,
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_soft_time_limit=cfg.celery_task_soft_time_limit_seconds,
        task_time_limit=cfg.celery_task_hard_time_limit_seconds,
        # Acknowledged after it finishes, requeued if the worker dies (tasks are idempotent).
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        result_expires=3600,
        broker_connection_retry_on_startup=True,
        beat_schedule=BEAT_SCHEDULE,
        # Never store task arguments or results that could hold document content in logs.
        worker_hijack_root_logger=False,
    )
    return app


celery_app = create_celery_app()


@worker_process_init.connect
def _limit_memory(**_: Any) -> None:
    """Optional address-space cap for each worker process (WORKER_MEMORY_LIMIT_MB, 0 = off). The
    container memory limit is the enforced cap; this turns a runaway parser into a MemoryError."""
    limit_mb = get_settings().worker_memory_limit_mb
    if limit_mb <= 0:
        return
    try:
        import resource

        limit = limit_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    except (ImportError, ValueError, OSError):
        logger.warning("worker_memory_limit_not_applied")


@task_failure.connect
def _log_task_failure(
    sender: Any = None, task_id: str | None = None, exception: BaseException | None = None, **_: Any
) -> None:
    """Log id, task name and a safe code only: no args, no exception text, no traceback."""
    logger.error(
        "task_failed",
        task=getattr(sender, "name", None),
        task_id=task_id,
        error_code=safe_error_code(exception) if exception else None,
    )
