"""GET /ai/status and the AI notice acknowledgement (D-54, D-58) used by the AI Tutor UI."""

import pytest
from httpx import AsyncClient

from app.ai.providers.fake_provider import FakeProvider
from app.core.config import Settings
from tests.ai.conftest import AiHarness, call
from tests.ai.test_provider_layer import make_settings
from tests.test_closeout_users_config import Actor, _call


class TestStatus:
    async def test_configured_status_never_leaks_secrets(
        self, client: AsyncClient, ai: AiHarness, alice: Actor
    ) -> None:
        ai.configure(llm_max_input_chars=1234)
        resp = await call(client, alice, "GET", "/status")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data == {
            "configured": True,
            "provider_display_name": FakeProvider.display_name,
            "is_test_provider": True,
            "max_input_chars": 1234,
        }

    async def test_unconfigured_is_200_not_503(
        self, client: AsyncClient, ai: AiHarness, alice: Actor
    ) -> None:
        ai.unconfigured()
        resp = await call(client, alice, "GET", "/status")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["configured"] is False and data["provider_display_name"] is None
        assert (await call(client, alice, "GET", "/models")).status_code == 503

    async def test_requires_authentication(self, client: AsyncClient, ai: AiHarness) -> None:
        assert (await client.get("/api/v1/ai/status")).status_code == 401


class TestNoticeAcknowledgement:
    async def test_acknowledge_is_stored_idempotent_and_per_user(
        self, client: AsyncClient, alice: Actor, bob: Actor
    ) -> None:
        prefs = (await _call(client, alice, "GET", "/users/me/preferences")).json()["data"]
        assert prefs["ai_notice_acknowledged_at"] is None

        first = await _call(client, alice, "POST", "/users/me/ai-notice/acknowledge")
        assert first.status_code == 200
        stamp = first.json()["data"]["ai_notice_acknowledged_at"]
        assert stamp is not None
        again = await _call(client, alice, "POST", "/users/me/ai-notice/acknowledge")
        assert again.json()["data"]["ai_notice_acknowledged_at"] == stamp  # first time is kept

        seen = (await _call(client, alice, "GET", "/users/me/preferences")).json()["data"]
        assert seen["ai_notice_acknowledged_at"] == stamp
        other = (await _call(client, bob, "GET", "/users/me/preferences")).json()["data"]
        assert other["ai_notice_acknowledged_at"] is None  # not shared with other users

    async def test_requires_authentication_and_csrf(
        self, client: AsyncClient, alice: Actor
    ) -> None:
        assert (await client.post("/api/v1/users/me/ai-notice/acknowledge")).status_code == 401
        no_csrf = await client.post("/api/v1/users/me/ai-notice/acknowledge", cookies=alice.cookies)
        assert no_csrf.status_code == 403


class TestFakeChunkDelay:
    def test_delay_comes_from_settings_and_is_bounded(self) -> None:
        provider = FakeProvider.create(
            make_settings(llm_provider="fake", fake_llm_chunk_delay_seconds=0.25)
        )
        assert provider.chunk_delay == 0.25
        with pytest.raises(ValueError):
            make_settings(fake_llm_chunk_delay_seconds=60)


def test_settings_default_has_no_delay() -> None:
    assert Settings.model_fields["fake_llm_chunk_delay_seconds"].default == 0.0
