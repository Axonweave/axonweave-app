"""Phase 6 M6.10: graph API, ownership, invalid relationships, traversal, merge."""

import uuid
from typing import Any

from httpx import AsyncClient

from tests.retrieval.test_search import Actor
from tests.test_closeout_users_config import _call


async def node(client: AsyncClient, who: Actor, name: str, **kw: Any) -> dict[str, Any]:
    body = {"workspace_id": str(who.ws.id), "name": name, "node_type": "concept", **kw}
    resp = await _call(client, who, "POST", "/knowledge/nodes", json=body)
    assert resp.status_code == 201, resp.text
    data: dict[str, Any] = resp.json()["data"]
    return data


async def edge(client: AsyncClient, who: Actor, a: str, b: str, kind: str = "RELATED_TO") -> Any:
    return await _call(
        client,
        who,
        "POST",
        "/knowledge/relationships",
        json={"source_node_id": a, "target_node_id": b, "relationship_type": kind},
    )


class TestGraph:
    async def test_create_list_and_detail(self, client: AsyncClient, alice: Actor) -> None:
        n = await node(client, alice, "Mitochondria", aliases=["Mitochondrion"])
        listed = (await _call(client, alice, "GET", "/knowledge/nodes")).json()
        assert listed["total"] == 1 and listed["data"][0]["id"] == n["id"]
        detail = (await _call(client, alice, "GET", f"/knowledge/nodes/{n['id']}")).json()["data"]
        assert detail["name"] == "Mitochondria" and "Mitochondrion" in detail["aliases"]

    async def test_relationship_rules(self, client: AsyncClient, alice: Actor) -> None:
        a, b = await node(client, alice, "A concept"), await node(client, alice, "B concept")
        assert (await edge(client, alice, a["id"], b["id"], "PREREQUISITE_OF")).status_code == 201
        # self loop, unknown type, missing node, duplicate
        assert (await edge(client, alice, a["id"], a["id"])).status_code in (400, 409, 422)
        bad = await edge(client, alice, a["id"], b["id"], "LOVES")
        assert bad.status_code == 422
        assert (await edge(client, alice, a["id"], str(uuid.uuid4()))).status_code == 404

    async def test_traversal_is_bounded_and_scoped(self, client: AsyncClient, alice: Actor) -> None:
        nodes = [await node(client, alice, f"Concept {i}") for i in range(4)]
        for x, y in zip(nodes, nodes[1:], strict=False):
            assert (await edge(client, alice, x["id"], y["id"])).status_code == 201
        resp = await _call(
            client, alice, "GET", f"/knowledge/graph/expand?node_id={nodes[0]['id']}&depth=1"
        )
        assert resp.status_code == 200
        ids = {n["id"] for n in resp.json()["data"]["nodes"]}
        assert nodes[0]["id"] in ids and nodes[3]["id"] not in ids
        too_deep = await _call(
            client, alice, "GET", f"/knowledge/graph/expand?node_id={nodes[0]['id']}&depth=99"
        )
        assert too_deep.status_code == 422

    async def test_merge_repoints_and_removes_duplicate(
        self, client: AsyncClient, alice: Actor
    ) -> None:
        keep, dup, other = [await node(client, alice, n) for n in ("Keep x", "Dup x", "Other x")]
        assert (await edge(client, alice, dup["id"], other["id"])).status_code == 201
        resp = await _call(
            client,
            alice,
            "POST",
            "/knowledge/nodes/merge",
            json={"survivor_id": keep["id"], "merged_id": dup["id"]},
        )
        assert resp.status_code == 200, resp.text
        assert (
            await _call(client, alice, "GET", f"/knowledge/nodes/{dup['id']}")
        ).status_code == 404
        detail = (await _call(client, alice, "GET", f"/knowledge/nodes/{keep['id']}")).json()[
            "data"
        ]
        assert detail["degree"] == 1


class TestOwnership:
    async def test_other_users_graph_is_invisible(
        self, client: AsyncClient, alice: Actor, bob: Actor
    ) -> None:
        mine = await node(client, alice, "Private concept")
        other = await node(client, bob, "Bob concept")
        assert (
            await _call(client, bob, "GET", f"/knowledge/nodes/{mine['id']}")
        ).status_code == 404
        assert (
            await _call(
                client,
                bob,
                "PATCH",
                f"/knowledge/nodes/{mine['id']}",
                json={"name": "Renamed concept"},
            )
        ).status_code == 404
        assert (
            await _call(client, bob, "DELETE", f"/knowledge/nodes/{mine['id']}")
        ).status_code == 404
        assert (await edge(client, bob, mine["id"], other["id"])).status_code == 404
        merged = await _call(
            client,
            bob,
            "POST",
            "/knowledge/nodes/merge",
            json={"survivor_id": other["id"], "merged_id": mine["id"]},
        )
        assert merged.status_code == 404
        assert (await _call(client, bob, "GET", "/knowledge/nodes")).json()["total"] == 1
        # the owner still has it, untouched
        assert (
            await _call(client, alice, "GET", f"/knowledge/nodes/{mine['id']}")
        ).status_code == 200

    async def test_cannot_create_in_foreign_workspace(
        self, client: AsyncClient, alice: Actor, bob: Actor
    ) -> None:
        resp = await _call(
            client,
            bob,
            "POST",
            "/knowledge/nodes",
            json={"workspace_id": str(alice.ws.id), "name": "Intruder", "node_type": "concept"},
        )
        assert resp.status_code == 404

    async def test_requires_authentication(self, client: AsyncClient) -> None:
        for path in (
            "/knowledge/nodes",
            "/knowledge/learner/dashboard",
            "/recommendations/learner",
        ):
            assert (await client.get(f"/api/v1{path}")).status_code == 401
