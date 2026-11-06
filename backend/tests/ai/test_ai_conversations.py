"""Conversation and model APIs (spec 14.1, 14.3)."""

import uuid

from httpx import AsyncClient

from tests.ai.conftest import AiHarness, call, new_conversation, send
from tests.test_closeout_users_config import Actor


class TestConversationCrud:
    async def test_create_works_before_any_message(
        self, client: AsyncClient, ai: AiHarness, alice: Actor
    ) -> None:
        resp = await call(client, alice, "POST", "/conversations", json={})
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert resp.json()["success"] is True
        assert data["status"] == "active" and data["title"] is None
        assert data["last_message_at"] is None
        messages = await call(client, alice, "GET", f"/conversations/{data['id']}/messages")
        assert messages.json()["data"] == [] and messages.json()["total"] == 0

    async def test_create_with_title_and_valid_model(
        self, client: AsyncClient, ai: AiHarness, alice: Actor
    ) -> None:
        resp = await call(
            client,
            alice,
            "POST",
            "/conversations",
            json={"title": "  Linear algebra  ", "model_id": "default"},
        )
        assert resp.status_code == 201
        assert resp.json()["data"]["title"] == "Linear algebra"

    async def test_create_with_invalid_model_is_rejected(
        self, client: AsyncClient, ai: AiHarness, alice: Actor
    ) -> None:
        resp = await call(client, alice, "POST", "/conversations", json={"model_id": "nope"})
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "LLM_INVALID_MODEL"

    async def test_get_rename_archive_delete(
        self, client: AsyncClient, ai: AiHarness, alice: Actor
    ) -> None:
        cid = await new_conversation(client, alice, title="Old")
        assert (await call(client, alice, "GET", f"/conversations/{cid}")).status_code == 200

        renamed = await call(
            client, alice, "PATCH", f"/conversations/{cid}", json={"title": " New "}
        )
        assert renamed.json()["data"]["title"] == "New"

        archived = await call(client, alice, "POST", f"/conversations/{cid}/archive")
        assert archived.json()["data"]["status"] == "archived"

        assert (await call(client, alice, "DELETE", f"/conversations/{cid}")).status_code == 204
        assert (await call(client, alice, "GET", f"/conversations/{cid}")).status_code == 404
        assert (await call(client, alice, "DELETE", f"/conversations/{cid}")).status_code == 404

    async def test_rename_rejects_blank_and_overlong_titles(
        self, client: AsyncClient, ai: AiHarness, alice: Actor
    ) -> None:
        cid = await new_conversation(client, alice, title="Keep")
        for title in ("   ", "", "x" * 201):
            resp = await call(
                client, alice, "PATCH", f"/conversations/{cid}", json={"title": title}
            )
            assert resp.status_code == 422
        assert (await call(client, alice, "GET", f"/conversations/{cid}")).json()["data"][
            "title"
        ] == "Keep"


class TestConversationList:
    async def test_orders_by_last_activity_and_paginates(
        self, client: AsyncClient, ai: AiHarness, alice: Actor
    ) -> None:
        first = await new_conversation(client, alice, title="first")
        second = await new_conversation(client, alice, title="second")
        third = await new_conversation(client, alice, title="third")
        # Newest-created is first until an older conversation receives a message.
        order = [
            c["id"] for c in (await call(client, alice, "GET", "/conversations")).json()["data"]
        ]
        assert order == [third, second, first]

        assert (await send(client, alice, first)).status_code == 201
        order = [
            c["id"] for c in (await call(client, alice, "GET", "/conversations")).json()["data"]
        ]
        assert order[0] == first

        page = (await call(client, alice, "GET", "/conversations?limit=2&offset=1")).json()
        assert page["total"] == 3 and page["limit"] == 2 and len(page["data"]) == 2

    async def test_limit_is_capped(self, client: AsyncClient, ai: AiHarness, alice: Actor) -> None:
        resp = await call(client, alice, "GET", "/conversations?limit=100000")
        assert resp.status_code == 422

    async def test_search_matches_title_and_escapes_wildcards(
        self, client: AsyncClient, ai: AiHarness, alice: Actor
    ) -> None:
        await new_conversation(client, alice, title="Calculus limits")
        await new_conversation(client, alice, title="100% sure")
        await new_conversation(client, alice, title="History")

        calc = (await call(client, alice, "GET", "/conversations?q=CALC")).json()
        assert [c["title"] for c in calc["data"]] == ["Calculus limits"]
        percent = (await call(client, alice, "GET", "/conversations?q=%25")).json()
        assert [c["title"] for c in percent["data"]] == ["100% sure"]  # not "match everything"
        underscore = (await call(client, alice, "GET", "/conversations?q=_")).json()
        assert underscore["data"] == []

    async def test_archived_hidden_by_default_and_filterable(
        self, client: AsyncClient, ai: AiHarness, alice: Actor
    ) -> None:
        keep = await new_conversation(client, alice, title="keep")
        old = await new_conversation(client, alice, title="old")
        await call(client, alice, "POST", f"/conversations/{old}/archive")
        active = (await call(client, alice, "GET", "/conversations")).json()["data"]
        assert [c["id"] for c in active] == [keep]
        archived = (await call(client, alice, "GET", "/conversations?status=archived")).json()
        assert [c["id"] for c in archived["data"]] == [old]

    async def test_unknown_id_is_404(
        self, client: AsyncClient, ai: AiHarness, alice: Actor
    ) -> None:
        resp = await call(client, alice, "GET", f"/conversations/{uuid.uuid4()}")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"


class TestModels:
    async def test_lists_only_safe_metadata(
        self, client: AsyncClient, ai: AiHarness, alice: Actor
    ) -> None:
        ai.configure(llm_allowed_models="other-model")
        resp = await call(client, alice, "GET", "/models")
        assert resp.status_code == 200
        models = resp.json()["data"]
        assert len(models) == 2 and sum(m["is_default"] for m in models) == 1
        for m in models:
            assert set(m) == {
                "id",
                "display_name",
                "is_default",
                "capabilities",
                "max_input_tokens",
                "max_output_tokens",
                "is_test_provider",
            }
            assert m["is_test_provider"] is True
        text = resp.text.lower()
        assert "api_key" not in text and "secret" not in text

    async def test_default_and_capabilities(
        self, client: AsyncClient, ai: AiHarness, alice: Actor
    ) -> None:
        default = (await call(client, alice, "GET", "/models/default")).json()["data"]
        assert default["is_default"] is True
        caps = (await call(client, alice, "GET", "/capabilities")).json()["data"]
        assert caps["streaming"] is True and caps["tool_calling"] is False

    async def test_not_configured_is_503_everywhere(
        self, client: AsyncClient, ai: AiHarness, alice: Actor
    ) -> None:
        ai.unconfigured()
        cid = await new_conversation(client, alice)  # creating an empty conversation still works
        for path in ("/models", "/models/default", "/capabilities"):
            resp = await call(client, alice, "GET", path)
            assert resp.status_code == 503, path
            assert resp.json()["error"]["code"] == "LLM_NOT_CONFIGURED"
        sent = await send(client, alice, cid)
        assert sent.status_code == 503
        assert sent.json()["error"]["code"] == "LLM_NOT_CONFIGURED"
        # Nothing was stored for the rejected send.
        listing = await call(client, alice, "GET", f"/conversations/{cid}/messages")
        assert listing.json()["total"] == 0
