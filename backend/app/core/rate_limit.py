"""
Rate limiting (D-18, superseded for multi-instance use by D-65).

`RateLimiter` is the interface every caller uses. Two implementations:

- `InProcessRateLimiter`: in-memory, per process. Used in tests, in development without Redis and as
  the degraded fallback.
- `RedisRateLimiter`: shared sliding window, correct across several API instances.

`ResilientRateLimiter` wraps a primary limiter with the in-process one. If Redis is unreachable it
neither fails open (no brute-force protection) nor rejects everything (the app would depend on
Redis): it limits per process, emits a security event (at most once a minute) and recovers
by itself.
"""

import asyncio
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Protocol

import structlog
from fastapi import HTTPException, Request
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings

_security_log = structlog.get_logger("security")


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
                raise _too_many(window_seconds)

            window.hits.append(now)

    def reset(self) -> None:
        """Clear all rate-limit counters. For use in tests only."""
        self._store.clear()


def _too_many(window_seconds: int) -> HTTPException:
    return HTTPException(
        status_code=429,
        detail={
            "code": "RATE_LIMIT_EXCEEDED",
            "message": "Too many requests. Please wait before trying again.",
        },
        headers={"Retry-After": str(window_seconds)},
    )


class RedisRateLimiter:
    """Sliding-window limiter on a Redis sorted set (shared by all API instances).

    Each hit is a member scored by wall-clock time. The add, trim and count run in one MULTI/EXEC
    transaction; if the count including this hit is over the limit the hit is removed again, so a
    rejected request does not extend the window.
    """

    _PREFIX = "rl:"

    def __init__(self, client: Any) -> None:
        self._redis: Any = client

    @classmethod
    def from_url(cls, url: str) -> "RedisRateLimiter":
        return cls(Redis.from_url(url, socket_connect_timeout=1, socket_timeout=1))

    async def check(self, key: str, limit: int, window_seconds: int) -> None:
        now = time.time()
        redis_key = f"{self._PREFIX}{key}"
        member = f"{now}:{uuid.uuid4().hex}"
        pipe = self._redis.pipeline(transaction=True)
        pipe.zremrangebyscore(redis_key, 0, now - window_seconds)
        pipe.zadd(redis_key, {member: now})
        pipe.zcard(redis_key)
        pipe.expire(redis_key, window_seconds + 1)
        results = await pipe.execute()
        if int(results[2]) > limit:
            await self._redis.zrem(redis_key, member)
            raise _too_many(window_seconds)

    async def clear_all(self) -> None:
        """Delete every limiter key. For tests only."""
        async for k in self._redis.scan_iter(match=f"{self._PREFIX}*"):
            await self._redis.delete(k)

    async def aclose(self) -> None:
        await self._redis.aclose()


class ResilientRateLimiter:
    """Primary limiter with an in-process fallback (D-65). See module docstring."""

    _LOG_EVERY_SECONDS = 60.0

    def __init__(self, primary: RateLimiter | None, fallback: InProcessRateLimiter) -> None:
        self._primary = primary
        self._fallback = fallback
        self._last_logged = 0.0

    async def check(self, key: str, limit: int, window_seconds: int) -> None:
        if self._primary is not None:
            try:
                await self._primary.check(key, limit, window_seconds)
                return
            except (RedisError, OSError, TimeoutError) as exc:
                self._note_degraded(type(exc).__name__)
        await self._fallback.check(key, limit, window_seconds)

    def _note_degraded(self, error_type: str) -> None:
        now = time.monotonic()
        if now - self._last_logged >= self._LOG_EVERY_SECONDS:
            self._last_logged = now
            _security_log.warning(
                "rate_limiter_degraded", backend="redis", fallback="in_process", error=error_type
            )

    def reset(self) -> None:
        """Clear in-process counters. For tests only."""
        self._fallback.reset()

    @property
    def primary(self) -> RateLimiter | None:
        return self._primary


def build_rate_limiter() -> ResilientRateLimiter:
    settings = get_settings()
    primary: RateLimiter | None = None
    if settings.rate_limit_backend.lower() == "redis" and settings.redis_url:
        primary = RedisRateLimiter.from_url(settings.redis_url)
    return ResilientRateLimiter(primary, InProcessRateLimiter())


# Module-level singleton, injected into routes via FastAPI Depends. Built on first use so importing
# this module never needs Redis.
_limiter: ResilientRateLimiter | None = None


def get_rate_limiter() -> ResilientRateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = build_rate_limiter()
    return _limiter


def get_client_ip(request: Request) -> str:
    """Client IP for rate limiting and audit logs.

    X-Forwarded-For is client-controlled unless a trusted reverse proxy overwrites it, so it is
    only honoured when TRUST_PROXY_HEADERS is enabled (set it only behind such a proxy).
    Otherwise any caller could dodge per-IP limits by sending a different value each request.
    """
    if get_settings().trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
