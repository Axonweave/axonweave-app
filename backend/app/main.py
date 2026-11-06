from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.ai.errors import AiError
from app.ai.model_registry import build_registry
from app.ai.providers.registry import close_providers
from app.ai.sync import sync_catalog_at_startup
from app.api.v1.router import router as api_v1_router
from app.core.config import AppEnv, get_settings
from app.core.csrf import CSRFMiddleware
from app.core.logging import CorrelationIdMiddleware, configure_logging, get_logger
from app.core.security_headers import SecurityHeadersMiddleware
from app.database.connection import AsyncSessionLocal

settings = get_settings()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging(json_logs=settings.app_env == AppEnv.production)
    logger.info(
        "axonweave_backend_starting",
        version=settings.app_version,
        env=settings.app_env.value,
    )
    await sync_catalog_at_startup(AsyncSessionLocal, build_registry(settings))
    yield
    await close_providers()
    logger.info("axonweave_backend_stopped")


app = FastAPI(
    title="Axonweave API",
    version=settings.app_version,
    docs_url="/docs" if settings.app_env != AppEnv.production else None,
    redoc_url="/redoc" if settings.app_env != AppEnv.production else None,
    lifespan=lifespan,
)

# ── Middleware (order matters: outermost applied last) ────────────────────────
# Starlette wraps in reverse order; SecurityHeaders runs first on response,
# CSRF+CORS+CorrelationId wrap it from the outside.

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CorrelationIdMiddleware)

app.add_middleware(
    CSRFMiddleware,
    frontend_url=settings.frontend_url,
    session_cookie=settings.cookie_name,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token", "X-Correlation-ID"],
    expose_headers=["X-Correlation-ID"],
)


# ── Exception handlers ────────────────────────────────────────────────────────


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Normalise all HTTP exceptions to {"success": false, "error": {...}}."""
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail:
        error = detail
    else:
        error = {"code": "HTTP_ERROR", "message": str(detail)}
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "error": error},
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(AiError)
async def ai_error_handler(request: Request, exc: AiError) -> JSONResponse:
    """AI errors carry a fixed code and message; provider text never reaches the client (D-49)."""
    http = exc.to_http_exception()
    return JSONResponse(
        status_code=http.status_code,
        content={"success": False, "error": http.detail},
        headers=http.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = exc.errors()
    # Pydantic v2 ctx["error"] can be an Exception instance — not JSON-serialisable
    for err in errors:
        ctx = err.get("ctx")
        if isinstance(ctx, dict) and isinstance(ctx.get("error"), Exception):
            ctx["error"] = str(ctx["error"])
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed.",
                "details": errors,
            },
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("unhandled_exception", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred.",
            },
        },
    )


# ── Routes ────────────────────────────────────────────────────────────────────


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok", "version": settings.app_version}


app.include_router(api_v1_router, prefix="/api/v1")
