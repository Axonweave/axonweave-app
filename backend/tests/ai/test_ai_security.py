"""Security and Phase 1 integration for the AI API (spec 22.5 cases 1-5, 10; D-51, D-53)."""

import json
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from structlog.testing import capture_logs

from app.ai.errors import LLMUnavailableError
from app.ai.providers.fake_provider import FakeProvider
from app.main import app
from app.models.ai_usage_record import AiUsageRecord
from app.models.conversation import Conversation
from app.models.message import Message, MessageFeedback
from app.repositories.ai_usage_repository import AiUsageRepository
from tests.ai.conftest import AiHarness, call, new_conversation, send
from tests.test_closeout_users_config import PASSWORD, Actor
from tests.test_closeout_users_config import _call as raw_call
from tests.test_spec_security_cases import _protected_operations


async def _conversation_with_answer(
    client: AsyncClient, who: Actor, content: str = "alice question"
) -> tuple[str, str]:
    cid = await new_conversation(client, who, title="Alice private chat")
    data = (await send(client, who, cid, content)).json()["data"]
    return cid, str(data["message"]["id"])


class TestAuthentication:
    def test_ai_routes_are_part_of_the_unauthenticated_sweep(self) -> None:
        # The sweep in test_spec_security_cases walks the OpenAPI schema, so every /ai route is
        # asserted to answer 401 without a session. Prove the routes are actually in that list.
        ai_ops = [op for op in _protected_operations() if op[1].startswith("/api/v1/ai/")]
        assert len(ai_ops) >= 12, ai_ops

    async def test_every_ai_route_needs_a_session(self, client: AsyncClient, ai: AiHarness) -> None:
        nil = str(uuid.UUID(int=0))
        ops = [op for op in _protected_operations() if op[1].startswith("/api/v1/ai/")]
        for method, path in ops:
            url = path.replace("{conversation_id}", nil).replace("{message_id}", nil)
            resp = await client.request(method, url, json={} if method != "GET" else None)
            assert resp.status_code in (401, 403), (method, path, resp.status_code)
            assert resp.status_code != 403 or "CSRF" in resp.text.upper()


class TestCrossUserAccess:
    """Bob must not be able to read, change, send to, rate or delete Alice's data (cases 1-3)."""

    async def test_every_route_returns_404_and_changes_nothing(
        self,
        client: AsyncClient,
        ai: AiHarness,
        fake: FakeProvider,
        db_session: AsyncSession,
        alice: Actor,
        bob: Actor,
    ) -> None:
        cid, mid = await _conversation_with_answer(client, alice)
        calls_before = len(fake.calls)

        attempts: list[tuple[str, str, dict[str, Any] | None, str]] = [
            ("GET", f"/conversations/{cid}", None, "CONVERSATION_NOT_FOUND"),
            ("PATCH", f"/conversations/{cid}", {"title": "hijacked"}, "CONVERSATION_NOT_FOUND"),
            ("POST", f"/conversations/{cid}/archive", None, "CONVERSATION_NOT_FOUND"),
            ("DELETE", f"/conversations/{cid}", None, "CONVERSATION_NOT_FOUND"),
            ("GET", f"/conversations/{cid}/messages", None, "CONVERSATION_NOT_FOUND"),
            (
                "POST",
                f"/conversations/{cid}/messages",
                {"content": "injected by bob", "stream": False},
                "CONVERSATION_NOT_FOUND",
            ),
            ("POST", f"/messages/{mid}/feedback", {"rating": "negative"}, "MESSAGE_NOT_FOUND"),
        ]
        for method, path, body, code in attempts:
            resp = await call(client, bob, method, path, json=body)
            assert resp.status_code == 404, (method, path, resp.text)
            assert resp.json()["error"]["code"] == code
            # Identical to asking for something that does not exist: existence is not leaked.
            ghost = path.replace(cid, str(uuid.uuid4())).replace(mid, str(uuid.uuid4()))
            twin = await call(client, bob, method, ghost, json=body)
            assert twin.status_code == 404 and twin.json() == resp.json()

        # Alice's data is exactly as she left it.
        db_session.expire_all()
        conv = (await db_session.execute(select(Conversation))).scalar_one()
        assert conv.title == "Alice private chat" and conv.status == "active"
        assert (await db_session.execute(select(func.count(Message.id)))).scalar_one() == 2
        assert (await db_session.execute(select(func.count(MessageFeedback.id)))).scalar_one() == 0
        assert len(fake.calls) == calls_before  # bob's send never reached the provider
        assert (await call(client, alice, "GET", f"/conversations/{cid}")).status_code == 200

    async def test_lists_and_search_never_include_other_users_conversations(
        self, client: AsyncClient, ai: AiHarness, alice: Actor, bob: Actor
    ) -> None:
        await _conversation_with_answer(client, alice)
        bobs = (await call(client, bob, "GET", "/conversations")).json()
        assert bobs["data"] == [] and bobs["total"] == 0
        found = (await call(client, bob, "GET", "/conversations?q=Alice")).json()
        assert found["data"] == []

    async def test_other_users_usage_is_invisible(
        self,
        client: AsyncClient,
        ai: AiHarness,
        db_session: AsyncSession,
        alice: Actor,
        bob: Actor,
    ) -> None:
        await _conversation_with_answer(client, alice)
        repo = AiUsageRepository(db_session)
        assert await repo.tokens_today(alice.user.id) > 0
        assert await repo.tokens_today(bob.user.id) == 0
        assert await repo.requests_today(bob.user.id) == 0

    async def test_bob_cannot_attach_a_message_to_alices_conversation_at_the_database(
        self, client: AsyncClient, ai: AiHarness, db_session: AsyncSession, alice: Actor, bob: Actor
    ) -> None:
        # Defence in depth: even a buggy query could not do it, the composite FK refuses (D-56).
        from sqlalchemy.exc import IntegrityError

        cid, _ = await _conversation_with_answer(client, alice)
        with pytest.raises(IntegrityError):
            async with db_session.begin_nested():
                db_session.add(
                    Message(
                        conversation_id=uuid.UUID(cid),
                        user_id=bob.user.id,
                        role="user",
                        status="completed",
                        sequence_number=99,
                        content="x",
                    )
                )
                await db_session.flush()


class TestLogsStayFreeOfContent:
    async def test_no_message_text_prompt_or_reply_in_logs(
        self,
        client: AsyncClient,
        ai: AiHarness,
        fake: FakeProvider,
        caplog: pytest.LogCaptureFixture,
        alice: Actor,
    ) -> None:
        marker_in, marker_out = "PRIVATE-QUESTION-7788", "PRIVATE-ANSWER-9911"
        fake.reply = marker_out
        cid = await new_conversation(client, alice)
        with capture_logs() as events, caplog.at_level("DEBUG"):
            assert (await send(client, alice, cid, marker_in)).status_code == 201
            fake.fail_with = LLMUnavailableError()
            ai.configure(llm_max_retries=0)
            await send(client, alice, cid, marker_in + " again")
        names = {e["event"] for e in events}
        assert {"ai_generation_completed", "ai_generation_failed", "ai_context_built"} <= names
        haystack = json.dumps(events, default=str) + caplog.text
        for secret in (marker_in, marker_out, "academic learning assistant"):
            assert secret not in haystack

    async def test_ai_events_carry_only_ids_counts_and_codes(
        self, client: AsyncClient, ai: AiHarness, alice: Actor
    ) -> None:
        cid = await new_conversation(client, alice)
        with capture_logs() as events:
            await send(client, alice, cid, "hello")
        done = next(e for e in events if e["event"] == "ai_generation_completed")
        assert set(done) <= {
            "event",
            "log_level",
            "conversation_id",
            "message_id",
            "model",
            "input_tokens",
            "output_tokens",
            "finish_reason",
            "duration_ms",
        }


class TestApiSurface:
    def test_openapi_exposes_no_provider_credentials(self) -> None:
        schema = json.dumps(app.openapi()).lower()
        for needle in ("gemini_api_key", "api_key", "secretstr"):
            assert needle not in schema


class TestPhase1Integration:
    async def test_export_contains_own_ai_data_only(
        self, client: AsyncClient, ai: AiHarness, alice: Actor, bob: Actor
    ) -> None:
        cid, mid = await _conversation_with_answer(client, alice, "alice-export-question")
        await call(client, alice, "POST", f"/messages/{mid}/feedback", json={"rating": "positive"})
        await _conversation_with_answer(client, bob, "bob-secret-question")

        data = (await raw_call(client, alice, "GET", "/users/me/export")).json()["data"]
        conversations = data["ai_conversations"]
        assert [c["id"] for c in conversations] == [cid]
        messages = conversations[0]["messages"]
        assert [m["role"] for m in messages] == ["user", "assistant"]
        assert messages[0]["content"] == "alice-export-question"
        assert messages[1]["feedback"]["rating"] == "positive"
        assert len(data["ai_usage"]) == 1 and "content" not in data["ai_usage"][0]
        assert "bob-secret-question" not in json.dumps(data)

    async def test_export_with_no_ai_use_is_empty_not_missing(
        self, client: AsyncClient, ai: AiHarness, alice: Actor
    ) -> None:
        data = (await raw_call(client, alice, "GET", "/users/me/export")).json()["data"]
        assert data["ai_conversations"] == [] and data["ai_usage"] == []

    async def test_account_deletion_removes_all_ai_data_but_only_for_that_user(
        self,
        client: AsyncClient,
        ai: AiHarness,
        db_session: AsyncSession,
        alice: Actor,
        bob: Actor,
    ) -> None:
        cid, mid = await _conversation_with_answer(client, alice)
        await call(client, alice, "POST", f"/messages/{mid}/feedback", json={"rating": "positive"})
        bob_cid, _ = await _conversation_with_answer(client, bob, "bob keeps this")
        alice_id = alice.user.id

        resp = await raw_call(
            client,
            alice,
            "DELETE",
            "/users/me",
            json={"password": PASSWORD, "confirmation": "delete my account"},
        )
        assert resp.status_code == 200
        db_session.expire_all()
        for model in (Conversation, Message, MessageFeedback, AiUsageRecord):
            count = (
                await db_session.execute(
                    select(func.count()).select_from(model).where(model.user_id == alice_id)
                )
            ).scalar_one()
            assert count == 0, model.__name__
        assert (await call(client, bob, "GET", f"/conversations/{bob_cid}")).status_code == 200
        assert (await db_session.execute(select(func.count(AiUsageRecord.id)))).scalar_one() == 1

    async def test_deleting_a_conversation_keeps_usage_with_null_links(
        self, client: AsyncClient, ai: AiHarness, db_session: AsyncSession, alice: Actor
    ) -> None:
        cid, _ = await _conversation_with_answer(client, alice)
        alice_id = alice.user.id
        assert (await call(client, alice, "DELETE", f"/conversations/{cid}")).status_code == 204
        db_session.expire_all()
        record = (await db_session.execute(select(AiUsageRecord))).scalar_one()
        assert record.conversation_id is None and record.message_id is None
        assert record.user_id == alice_id and record.input_tokens is not None
        assert (await db_session.execute(select(func.count(Message.id)))).scalar_one() == 0
