"""Safe error codes for background tasks (D-68, spec 17.3).

Only these codes reach the database or the client: never stack traces, file paths, SQL or document
text.
"""

from celery.exceptions import SoftTimeLimitExceeded

from app.storage.base import StorageError

# Codes a job may record in `document_processing_jobs.error_code` (more arrive with the M3 stages).
INTERNAL = "INTERNAL"
TASK_TIMEOUT = "TASK_TIMEOUT"
WORKER_LOST = "WORKER_LOST"
STORAGE_UNAVAILABLE = "STORAGE_UNAVAILABLE"
INVALID_STORAGE_KEY = "INVALID_STORAGE_KEY"


class TransientTaskError(Exception):
    """Raised by a task for a failure worth retrying (network blip, store briefly down)."""


def safe_error_code(exc: BaseException) -> str:
    """Map any exception to a short code that is safe to store and log."""
    if isinstance(exc, SoftTimeLimitExceeded):
        return TASK_TIMEOUT
    if isinstance(exc, StorageError):
        return exc.code
    if isinstance(exc, TransientTaskError):
        return STORAGE_UNAVAILABLE
    return INTERNAL
