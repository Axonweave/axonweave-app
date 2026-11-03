"""Security response headers middleware (D-31).

Adds headers to every response:
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
  X-Frame-Options: DENY  (belt-and-suspenders alongside CSP frame-ancestors)
  Cache-Control: no-store  (on authenticated / API responses)
  Permissions-Policy: restrictive baseline
  Strict-Transport-Security (production only)
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.config import AppEnv, get_settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self._production = get_settings().app_env == AppEnv.production

    async def dispatch(self, request: Request, call_next: object) -> Response:
        response: Response = await call_next(request)  # type: ignore[operator]

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
        )

        # No-store on /api/ routes (all authenticated endpoints)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"

        if self._production:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )

        return response
