"""
In-process rate limiter (D-18).

No Redis in Phase 1. Backed by a simple in-memory store so it can be swapped
to a Redis-backed implementation without changing call sites.

NOTE: this limiter is per-process. Multi-instance deployments need the Redis backend.
"""

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Protocol

from fastapi import HTTPException, Request


class RateLimiter(Protocol):
    """Interface for rate-limiter backends (swap to Redis later)."""

    async def check(self, key: str, limit: int, window_seconds: int) -> None:
        """Raise HTTP 429 if the key has exceeded limit hits in window_seconds."""
        ...


@dataclass
class _Window:
    hits: deque[float] = field(default_factory=deque)


class InProcessRateLimiter:
    """Fixed-window rate limiter backed by in-process memory.

    Not suitable for multi-replica deployments without a shared backend.
    """

    def __init__(self) -> None:
        self._store: dict[str, _Window] = {}
        self._lock = asyncio.Lock()

    async def check(self, key: str, limit: int, window_seconds: int) -> None:
        now = time.monotonic()
        cutoff = now - window_seconds

        async with self._lock:
            window = self._store.setdefault(key, _Window())
            while window.hits and window.hits[0] < cutoff:
                window.hits.popleft()

            if len(window.hits) >= limit:
                raise HTTPException(
                    status_code=429,
                    detail={
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": "Too many requests. Please wait before trying again.",
                    },
                    headers={"Retry-After": str(window_seconds)},
                )

            window.hits.append(now)


# Module-level singleton — injected into routes via FastAPI Depends
_limiter = InProcessRateLimiter()


def get_rate_limiter() -> InProcessRateLimiter:
    return _limiter


def get_client_ip(request: Request) -> str:
    """Return best-effort client IP from X-Forwarded-For or direct connection."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
