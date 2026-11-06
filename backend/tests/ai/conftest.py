"""Shared fixtures for the AI API tests. They use the fake provider only: no network, no cost."""

from collections.abc import Generator
from dataclasses import dataclass
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.model_registry import build_registry
from app.ai.orchestration import service as orchestration
from app.ai.orchestration.runtime import AiRuntime, get_ai_runtime, get_session_factory
from app.ai.orchestration.streaming import get_generation_registry
from app.ai.providers.base import LLMProvider
from app.ai.providers.fake_provider import FakeProvider
from app.core.rate_limit import get_rate_limiter
from app.main import app
from tests.ai.test_provider_layer import make_settings
from tests.conftest import _TestSessionLocal
from tests.test_closeout_users_config import Actor, _actor, _call

API = "/ai"


@dataclass
class AiHarness:
    """Swap the runtime the routes use, e.g. to change a limit for one test."""

    provider: LLMProvider

    def configure(self, **settings: Any) -> AiRuntime:
        base: dict[str, Any] = {
            "llm_provider": "fake",
            "ai_requests_per_minute_per_user": 1000,
            "ai_daily_message_quota": 1000,
            "ai_daily_token_quota": 10_000_000,
        }
        cfg = make_settings(**{**base, **settings})
        runtime = AiRuntime(cfg, build_registry(cfg), lambda: self.provider)
        app.dependency_overrides[get_ai_runtime] = lambda: runtime
        return runtime

    def unconfigured(self) -> None:
        cfg = make_settings()  # no LLM_PROVIDER
        runtime = AiRuntime(cfg, build_registry(cfg), lambda: self.provider)
        app.dependency_overrides[get_ai_runtime] = lambda: runtime

    def use(self, provider: LLMProvider) -> None:
        self.provider = provider


@pytest.fixture
def fake() -> FakeProvider:
    return FakeProvider()


@pytest.fixture
def ai(
    client: AsyncClient, fake: FakeProvider, monkeypatch: pytest.MonkeyPatch
) -> Generator[AiHarness]:
    monkeypatch.setattr(orchestration, "RETRY_BASE_DELAY", 0.0)
    get_rate_limiter().reset()
    get_generation_registry().clear()
    app.dependency_overrides[get_session_factory] = lambda: _TestSessionLocal
    harness = AiHarness(fake)
    harness.configure()
    yield harness
    app.dependency_overrides.pop(get_session_factory, None)
    get_generation_registry().clear()
    app.dependency_overrides.pop(get_ai_runtime, None)


@pytest.fixture
async def alice(db_session: AsyncSession) -> Actor:
    return await _actor(db_session, "alice-ai@example.com")


@pytest.fixture
async def bob(db_session: AsyncSession) -> Actor:
    return await _actor(db_session, "bob-ai@example.com")


async def call(client: AsyncClient, who: Actor, method: str, path: str, **kw: Any) -> Any:
    return await _call(client, who, method, f"{API}{path}", **kw)


async def new_conversation(client: AsyncClient, who: Actor, **body: Any) -> str:
    resp = await call(client, who, "POST", "/conversations", json=body)
    assert resp.status_code == 201, resp.text
    return str(resp.json()["data"]["id"])


async def send(
    client: AsyncClient, who: Actor, conversation_id: str, content: str = "hello", **body: Any
) -> Any:
    return await call(
        client,
        who,
        "POST",
        f"/conversations/{conversation_id}/messages",
        json={"content": content, "stream": False, **body},
    )
