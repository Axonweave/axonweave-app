"""CSRF protection middleware — D-04 double-submit cookie pattern."""

from collections.abc import Awaitable, Callable
from urllib.parse import urlparse

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.security import constant_time_compare
from app.core.security_logging import log_csrf_failure

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})
CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "x-csrf-token"


def _origin_allowed(origin: str, allowed_url: str) -> bool:
    parsed = urlparse(allowed_url)
    allowed_origin = f"{parsed.scheme}://{parsed.netloc}"
    return origin.rstrip("/") == allowed_origin.rstrip("/")


class CSRFMiddleware(BaseHTTPMiddleware):
    """
    Validates CSRF on state-changing requests that carry a session cookie.
    Safe methods and unauthenticated requests are skipped.
    """

    def __init__(self, app: object, frontend_url: str, session_cookie: str = "aw_session") -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._frontend_url = frontend_url
        self._session_cookie = session_cookie

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.method in _SAFE_METHODS:
            return await call_next(request)

        # Only check authenticated (cookie-bearing) requests
        if not request.cookies.get(self._session_cookie):
            return await call_next(request)

        # Validate Origin / Referer against allowlist
        origin = request.headers.get("origin") or request.headers.get("referer", "")
        if origin and not _origin_allowed(origin, self._frontend_url):
            ip = request.client.host if request.client else "unknown"
            log_csrf_failure(ip, request.url.path)
            return JSONResponse(
                status_code=403,
                content={
                    "success": False,
                    "error": {"code": "CSRF_ORIGIN_MISMATCH", "message": "Forbidden."},
                },
            )

        # Double-submit token check
        cookie_token = request.cookies.get(CSRF_COOKIE_NAME, "")
        header_token = request.headers.get(CSRF_HEADER_NAME, "")

        if not cookie_token or not header_token:
            ip = request.client.host if request.client else "unknown"
            log_csrf_failure(ip, request.url.path)
            return JSONResponse(
                status_code=403,
                content={
                    "success": False,
                    "error": {"code": "CSRF_TOKEN_MISSING", "message": "Forbidden."},
                },
            )

        if not constant_time_compare(cookie_token, header_token):
            ip = request.client.host if request.client else "unknown"
            log_csrf_failure(ip, request.url.path)
            return JSONResponse(
                status_code=403,
                content={
                    "success": False,
                    "error": {"code": "CSRF_TOKEN_INVALID", "message": "Forbidden."},
                },
            )

        return await call_next(request)
