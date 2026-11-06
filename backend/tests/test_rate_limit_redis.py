"""Redis rate limiter behind the existing RateLimiter interface (D-65).

Unit tests use fakeredis; one test talks to the real Redis from the compose/CI stack when
REDIS_URL is available. The Phase 1/2 limiter tests keep running against the in-process backend.
"""

import asyncio

import fakeredis
import pytest
import pytest_asyncio
from fastapi import HTTPException
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core.rate_limit import (
    InProcessRateLimiter,
    RateLimiter,
    RedisRateLimiter,
    ResilientRateLimiter,
    build_rate_limiter,
)
from tests import AMBIENT_REDIS_URL
from tests.ai.test_provider_layer import make_settings


@pytest_asyncio.fixture
async def redis_limiter() -> RedisRateLimiter:
    client = fakeredis.FakeAsyncRedis()
    limiter = RedisRateLimiter(client)
    yield limiter  # type: ignore[misc]
    await client.flushall()
    await client.aclose()


async def _exhaust(limiter: RateLimiter, key: str, limit: int, window: int = 60) -> HTTPException:
    for _ in range(limit):
        await limiter.check(key, limit, window)
    with pytest.raises(HTTPException) as info:
        await limiter.check(key, limit, window)
    return info.value


async def test_allows_up_to_the_limit_then_429_with_retry_after(
    redis_limiter: RedisRateLimiter,
) -> None:
    exc = await _exhaust(redis_limiter, "login:1.2.3.4", 3, 30)
    assert exc.status_code == 429
    assert exc.detail["code"] == "RATE_LIMIT_EXCEEDED"  # type: ignore[index]
    assert exc.headers == {"Retry-After": "30"}


async def test_keys_are_independent(redis_limiter: RedisRateLimiter) -> None:
    await _exhaust(redis_limiter, "a", 2)
    await redis_limiter.check("b", 2, 60)  # another key is unaffected


async def test_rejected_requests_do_not_extend_the_window(redis_limiter: RedisRateLimiter) -> None:
    await _exhaust(redis_limiter, "k", 2, 60)
    for _ in range(5):
        with pytest.raises(HTTPException):
            await redis_limiter.check("k", 2, 60)
    # Only the two accepted hits are stored.
    assert await redis_limiter._redis.zcard("rl:k") == 2


async def test_window_slides(redis_limiter: RedisRateLimiter) -> None:
    await _exhaust(redis_limiter, "slide", 2, 1)
    await asyncio.sleep(1.2)
    await redis_limiter.check("slide", 2, 1)  # old hits have left the window


async def test_concurrent_checks_never_exceed_the_limit(redis_limiter: RedisRateLimiter) -> None:
    results = await asyncio.gather(
        *[redis_limiter.check("burst", 5, 60) for _ in range(20)], return_exceptions=True
    )
    accepted = [r for r in results if r is None]
    rejected = [r for r in results if isinstance(r, HTTPException)]
    assert len(accepted) == 5 and len(rejected) == 15


async def test_limits_are_shared_between_two_instances() -> None:
    """The reason for Redis: two API processes see one counter."""
    server = fakeredis.FakeServer()
    a = RedisRateLimiter(fakeredis.FakeAsyncRedis(server=server))
    b = RedisRateLimiter(fakeredis.FakeAsyncRedis(server=server))
    await a.check("shared", 2, 60)
    await b.check("shared", 2, 60)
    with pytest.raises(HTTPException):
        await a.check("shared", 2, 60)


# ── degraded mode ────────────────────────────────────────────────────────────


class DownRedis:
    async def check(self, key: str, limit: int, window_seconds: int) -> None:
        raise RedisConnectionError("redis is down")


async def test_falls_back_to_in_process_limits_when_redis_is_down(
    caplog: pytest.LogCaptureFixture,
) -> None:
    limiter = ResilientRateLimiter(DownRedis(), InProcessRateLimiter())
    # Not fail-open: the limit still applies per process.
    exc = await _exhaust(limiter, "login:x", 3)
    assert exc.status_code == 429


async def test_down_redis_does_not_reject_everyone() -> None:
    limiter = ResilientRateLimiter(DownRedis(), InProcessRateLimiter())
    for i in range(10):
        await limiter.check(f"user-{i}", 1, 60)  # different keys all pass: not fail-closed


async def test_degraded_event_is_logged_once_and_without_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import rate_limit

    events: list[tuple[str, dict[str, object]]] = []

    class Recorder:
        def warning(self, event: str, **kw: object) -> None:
            events.append((event, kw))

    # A stub instead of reconfiguring structlog: the real logger is cached after first use.
    monkeypatch.setattr(rate_limit, "_security_log", Recorder())
    limiter = ResilientRateLimiter(DownRedis(), InProcessRateLimiter())
    for i in range(5):
        await limiter.check(f"k{i}", 10, 60)
    assert len(events) == 1  # rate-limited logging: not once per request
    name, fields = events[0]
    assert name == "rate_limiter_degraded"
    assert set(fields) == {"backend", "fallback", "error"}
    assert fields["error"] == "ConnectionError"  # the class only, never the message
    assert "redis is down" not in str(fields)


async def test_recovers_when_redis_comes_back() -> None:
    class Flaky:
        def __init__(self) -> None:
            self.down = True
            self.calls = 0

        async def check(self, key: str, limit: int, window_seconds: int) -> None:
            self.calls += 1
            if self.down:
                raise RedisConnectionError("down")

    flaky = Flaky()
    limiter = ResilientRateLimiter(flaky, InProcessRateLimiter())
    await limiter.check("k", 5, 60)
    flaky.down = False
    before = flaky.calls
    await limiter.check("k", 5, 60)
    assert flaky.calls == before + 1  # the primary is used again without a restart


async def test_http_429_from_the_primary_is_not_swallowed_by_the_fallback() -> None:
    server = fakeredis.FakeServer()
    limiter = ResilientRateLimiter(
        RedisRateLimiter(fakeredis.FakeAsyncRedis(server=server)), InProcessRateLimiter()
    )
    exc = await _exhaust(limiter, "k", 2)
    assert exc.status_code == 429


# ── factory ──────────────────────────────────────────────────────────────────


def test_memory_backend_is_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core import rate_limit

    monkeypatch.setattr(
        rate_limit, "get_settings", lambda: make_settings(rate_limit_backend="memory")
    )
    assert build_rate_limiter().primary is None


def test_redis_backend_is_selected_by_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core import rate_limit

    monkeypatch.setattr(
        rate_limit,
        "get_settings",
        lambda: make_settings(rate_limit_backend="redis", redis_url="redis://localhost:6379/0"),
    )
    assert isinstance(build_rate_limiter().primary, RedisRateLimiter)


@pytest.mark.skipif(not AMBIENT_REDIS_URL, reason="no Redis configured")
async def test_against_the_real_redis_of_the_stack() -> None:
    limiter = RedisRateLimiter.from_url(AMBIENT_REDIS_URL)
    key = "pytest:real-redis"
    try:
        await limiter.clear_all()
        exc = await _exhaust(limiter, key, 3, 30)
        assert exc.status_code == 429
    finally:
        await limiter.clear_all()
        await limiter.aclose()
