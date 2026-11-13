"""Phase 7 M7.1: research projects (CRUD, validation, ownership, archive, persistence)."""

import uuid
from typing import Any

from httpx import AsyncClient

from tests.retrieval.test_search import Actor
from tests.test_closeout_users_config import _call


async def make(client: AsyncClient, who: Actor, **kw: Any) -> dict[str, Any]:
    body = {"workspace_id": str(who.ws.id), "title": "Protein folding review", **kw}
    resp = await _call(client, who, "POST", "/research/projects", json=body)
    assert resp.status_code == 201, resp.text
    data: dict[str, Any] = resp.json()["data"]
    return data


async def get(client: AsyncClient, who: Actor, path: str) -> Any:
    return await _call(client, who, "GET", f"/research/projects{path}")


class TestProjects:
    async def test_create_read_update_and_persist(self, client: AsyncClient, alice: Actor) -> None:
        p = await make(
            client,
            alice,
            domain="Biochemistry",
            research_problem="How do chaperones help folding?",
            objectives=["Map methods", "  Map methods ", "Compare datasets"],
            research_questions=["What limits accuracy?"],
            keywords=["protein", "folding", "protein"],
            start_date="2026-01-01",
            target_date="2026-06-30",
        )
        assert p["status"] == "planning" and p["archived_at"] is None
        assert p["objectives"] == ["Map methods", "Compare datasets"]  # cleaned, deduplicated
        assert p["keywords"] == ["protein", "folding"]
        got = (await get(client, alice, f"/{p['id']}")).json()["data"]
        assert got["title"] == "Protein folding review"
        upd = await _call(
            client,
            alice,
            "PATCH",
            f"/research/projects/{p['id']}",
            json={"status": "active", "description": "Scope notes", "domain": None},
        )
        assert upd.status_code == 200
        data = upd.json()["data"]
        assert data["status"] == "active" and data["description"] == "Scope notes"
        assert data["domain"] is None and data["objectives"] == p["objectives"]

    async def test_validation(self, client: AsyncClient, alice: Actor) -> None:
        ws = str(alice.ws.id)
        bad = [
            {"workspace_id": ws, "title": "x"},
            {"workspace_id": ws, "title": "Fine title", "status": "done"},
            {"workspace_id": ws, "title": "Fine title", "extra": 1},
            {"workspace_id": ws, "title": "Fine title", "objectives": ["a"] * 21},
            {
                "workspace_id": ws,
                "title": "Fine title",
                "start_date": "2026-05-01",
                "target_date": "2026-04-01",
            },
        ]
        for body in bad:
            resp = await _call(client, alice, "POST", "/research/projects", json=body)
            assert resp.status_code == 422, body
        p = await make(client, alice, start_date="2026-05-01")
        url = f"/research/projects/{p['id']}"
        resp = await _call(client, alice, "PATCH", url, json={"target_date": "2026-04-01"})
        assert resp.status_code == 422
        # a required field cannot be cleared with null: the change is ignored
        resp = await _call(client, alice, "PATCH", url, json={"title": None})
        assert resp.status_code == 200
        assert (await get(client, alice, f"/{p['id']}")).json()["data"]["title"] == p["title"]

    async def test_list_filters_sort_and_pagination(
        self, client: AsyncClient, alice: Actor
    ) -> None:
        await make(client, alice, title="Alpha study", status="active")
        await make(client, alice, title="Beta study", domain="Physics")
        await make(client, alice, title="Gamma survey")
        listed = (await get(client, alice, "?sort_by=title&sort_dir=asc")).json()
        assert [p["title"] for p in listed["data"]] == ["Alpha study", "Beta study", "Gamma survey"]
        assert listed["total"] == 3
        assert (await get(client, alice, "?status=active")).json()["total"] == 1
        found = (await get(client, alice, "?q=physics")).json()
        assert [p["title"] for p in found["data"]] == ["Beta study"]
        assert (await get(client, alice, "?q=%25")).json()["total"] == 0  # wildcards escaped
        page = (await get(client, alice, "?limit=2&offset=2&sort_by=title&sort_dir=asc")).json()
        assert len(page["data"]) == 1 and page["total"] == 3
        for bad in ("limit=101", "sort_by=password", "sort_dir=sideways", "status=nope"):
            assert (await get(client, alice, f"?{bad}")).status_code == 422

    async def test_archive_restore_delete(self, client: AsyncClient, alice: Actor) -> None:
        p = await make(client, alice)
        url = f"/research/projects/{p['id']}"
        assert (await _call(client, alice, "POST", f"{url}/restore")).status_code == 409
        arch = await _call(client, alice, "POST", f"{url}/archive")
        assert arch.status_code == 200 and arch.json()["data"]["archived_at"]
        assert (await get(client, alice, "")).json()["total"] == 0
        assert (await get(client, alice, "?archived=true")).json()["total"] == 1
        edit = await _call(client, alice, "PATCH", url, json={"title": "Changed title"})
        assert edit.status_code == 409
        assert (await _call(client, alice, "POST", f"{url}/restore")).status_code == 200
        assert (await _call(client, alice, "DELETE", url)).status_code == 204
        assert (await _call(client, alice, "GET", url)).status_code == 404


class TestOwnership:
    async def test_other_users_cannot_see_or_change_a_project(
        self, client: AsyncClient, alice: Actor, bob: Actor
    ) -> None:
        p = await make(client, alice)
        url = f"/research/projects/{p['id']}"
        assert (await _call(client, bob, "GET", url)).status_code == 404
        patch = await _call(client, bob, "PATCH", url, json={"title": "Hijacked title"})
        assert patch.status_code == 404
        assert (await _call(client, bob, "POST", f"{url}/archive")).status_code == 404
        assert (await _call(client, bob, "POST", f"{url}/restore")).status_code == 404
        assert (await _call(client, bob, "DELETE", url)).status_code == 404
        assert (await get(client, bob, "")).json()["total"] == 0
        still = (await _call(client, alice, "GET", url)).json()["data"]
        assert still["title"] == "Protein folding review" and still["archived_at"] is None

    async def test_cannot_use_a_foreign_or_unknown_workspace(
        self, client: AsyncClient, alice: Actor, bob: Actor
    ) -> None:
        for ws in (str(alice.ws.id), str(uuid.uuid4())):
            resp = await _call(
                client,
                bob,
                "POST",
                "/research/projects",
                json={"workspace_id": ws, "title": "Intruder project"},
            )
            assert resp.status_code == 404
            assert (await get(client, bob, f"?workspace_id={ws}")).status_code == 404

    async def test_requires_authentication(self, client: AsyncClient) -> None:
        assert (await client.get("/api/v1/research/projects")).status_code == 401
        assert (await client.post("/api/v1/research/projects", json={})).status_code in (401, 403)
