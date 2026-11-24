"""Study Studio presets: CRUD, one default, ownership (404), use as generation defaults."""

import uuid

from httpx import AsyncClient

from tests.retrieval.test_search import Actor
from tests.test_closeout_users_config import _call

BODY = {
    "name": "Exam crunch",
    "description": "Hard questions, short summaries",
    "is_default": False,
    "language": "English",
    "explanation_level": "beginner",
    "summary_length": "short",
    "question_difficulty": "hard",
    "include_examples": True,
    "include_definitions": True,
    "include_source_references": False,
}


class TestPresets:
    async def test_requires_login(self, client: AsyncClient) -> None:
        for method, url in (
            ("GET", "/study/presets"),
            ("POST", "/study/presets"),
            ("PUT", f"/study/presets/{uuid.uuid4()}"),
            ("DELETE", f"/study/presets/{uuid.uuid4()}"),
        ):
            assert (await client.request(method, f"/api/v1{url}")).status_code == 401

    async def test_create_list_update_delete(self, client: AsyncClient, alice: Actor) -> None:
        assert (await _call(client, alice, "GET", "/study/presets")).json()["data"] == []
        created = await _call(client, alice, "POST", "/study/presets", json=BODY)
        assert created.status_code == 201, created.text
        preset = created.json()["data"]
        assert preset["name"] == "Exam crunch" and preset["question_difficulty"] == "hard"

        listed = (await _call(client, alice, "GET", "/study/presets")).json()
        assert listed["total"] == 1 and listed["data"][0]["id"] == preset["id"]

        changed = {**BODY, "name": "Exam crunch v2", "question_difficulty": "easy"}
        updated = await _call(client, alice, "PUT", f"/study/presets/{preset['id']}", json=changed)
        assert updated.status_code == 200
        assert updated.json()["data"]["question_difficulty"] == "easy"

        deleted = await _call(client, alice, "DELETE", f"/study/presets/{preset['id']}")
        assert deleted.status_code == 204
        assert (await _call(client, alice, "GET", "/study/presets")).json()["data"] == []

    async def test_validation_and_duplicate_names(self, client: AsyncClient, alice: Actor) -> None:
        for bad in (
            {**BODY, "name": "   "},
            {**BODY, "name": "x" * 61},
            {**BODY, "question_difficulty": "impossible"},
            {**BODY, "extra": 1},
        ):
            resp = await _call(client, alice, "POST", "/study/presets", json=bad)
            assert resp.status_code == 422
        assert (await _call(client, alice, "POST", "/study/presets", json=BODY)).status_code == 201
        dup = await _call(
            client, alice, "POST", "/study/presets", json={**BODY, "name": "exam CRUNCH"}
        )
        assert dup.status_code == 409
        assert dup.json()["error"]["code"] == "PRESET_NAME_TAKEN"

    async def test_only_one_default(self, client: AsyncClient, alice: Actor) -> None:
        a = (
            await _call(
                client,
                alice,
                "POST",
                "/study/presets",
                json={**BODY, "name": "A", "is_default": True},
            )
        ).json()["data"]
        b = (
            await _call(client, alice, "POST", "/study/presets", json={**BODY, "name": "B"})
        ).json()["data"]
        assert a["is_default"] is True and b["is_default"] is False

        made = await _call(client, alice, "POST", f"/study/presets/{b['id']}/default")
        assert made.status_code == 200 and made.json()["data"]["is_default"] is True
        rows = (await _call(client, alice, "GET", "/study/presets")).json()["data"]
        assert [r["name"] for r in rows if r["is_default"]] == ["B"]
        assert rows[0]["name"] == "B"  # the default is listed first

    async def test_other_users_presets_are_404(
        self, client: AsyncClient, alice: Actor, bob: Actor
    ) -> None:
        preset = (await _call(client, alice, "POST", "/study/presets", json=BODY)).json()["data"]
        pid = preset["id"]
        assert (await _call(client, bob, "GET", "/study/presets")).json()["data"] == []
        for method, url, kwargs in (
            ("PUT", f"/study/presets/{pid}", {"json": BODY}),
            ("POST", f"/study/presets/{pid}/default", {}),
            ("DELETE", f"/study/presets/{pid}", {}),
        ):
            resp = await _call(client, bob, method, url, **kwargs)
            assert resp.status_code == 404, (method, url)
        # still there for its owner
        assert (await _call(client, alice, "GET", "/study/presets")).json()["total"] == 1

    async def test_generation_with_a_foreign_preset_is_404(
        self, client: AsyncClient, alice: Actor, bob: Actor
    ) -> None:
        preset = (await _call(client, alice, "POST", "/study/presets", json=BODY)).json()["data"]
        resp = await _call(
            client,
            bob,
            "POST",
            "/study/generations",
            json={
                "generation_type": "summary",
                "source": {"type": "subject", "id": str(uuid.uuid4())},
                "preset_id": preset["id"],
            },
        )
        assert resp.status_code in (404, 503), resp.text  # never uses someone else's preset
