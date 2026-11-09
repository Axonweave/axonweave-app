"""Background processing (Phase 3). Runs in the Celery worker; the API only enqueues.

The API process never imports parser libraries (D-70): they are installed in the worker image only,
and the parsers themselves arrive in M3.
"""
