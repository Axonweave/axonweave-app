"""Opt-in live check: one real streamed request through the real SSE endpoint.

Skipped unless a provider is configured in the environment. It spends a few tokens. Run with
`pytest -m live tests/ai/test_live_streaming.py`. It prints no key and no message text.
"""

from collections.abc import Iterator

import pytest
from httpx import AsyncClient

from app.ai.orchestration.runtime import get_ai_runtime, get_session_factory
from app.ai.orchestration.streaming import get_generation_registry
from app.core.config import get_settings
from app.main import app
from tests.ai.conftest import call, new_conversation
from tests.ai.test_ai_streaming import names, parse_sse, usage_rows
from tests.conftest import _TestSessionLocal
from tests.test_closeout_users_config import Actor

pytestmark = pytest.mark.live


@pytest.fixture(autouse=True)
def _real_provider() -> Iterator[None]:
    settings = get_settings()
    if settings.llm_provider in (None, "", "fake") or settings.gemini_api_key is None:
        pytest.skip("no real provider configured")
    app.dependency_overrides.pop(get_ai_runtime, None)
    # The stream task opens its own session: point it at the test database, never the app one.
    app.dependency_overrides[get_session_factory] = lambda: _TestSessionLocal
    get_generation_registry().clear()
    yield
    app.dependency_overrides.pop(get_session_factory, None)


async def test_real_stream_through_sse_endpoint(client: AsyncClient, alice: Actor) -> None:
    cid = await new_conversation(client, alice)
    resp = await call(
        client,
        alice,
        "POST",
        f"/conversations/{cid}/messages",
        json={"content": "Reply with one short sentence about triangles.", "stream": True},
    )
    assert resp.status_code == 200, resp.text
    frames = parse_sse(resp.text)
    order = names(frames)
    assert order[0] == "message.started" and order[-1] == "message.completed"
    assert order.count("message.delta") >= 1
    row = (await usage_rows(alice.user.id))[0]
    assert row.request_status == "success" and row.usage_source is not None
    print(f"deltas={order.count('message.delta')} source={row.usage_source}")
