"""Phase 7 M7.5: evidence matrices (columns, entries, origins, evidence links, access)."""

import uuid
from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.research.test_comparisons import (
    DATASET_A,
    METRIC,
    RESULT_A,
    analysed_paper,
)
from tests.research.test_projects_api import make as make_project
from tests.retrieval.test_search import Actor
from tests.study.conftest import Harness
from tests.test_closeout_users_config import _call

MODEL = {
    "label": "Model",
    "text": "A chloroplast model is used.",
    "origin": "reported",
    "confidence": 0.8,
    "evidence": [{"source": 1, "quote": "light energy"}],
}


async def build(
    client: AsyncClient, db: AsyncSession, who: Actor, lab: Harness
) -> tuple[str, str, str]:
    project = await make_project(client, who)
    paper = await analysed_paper(
        client,
        db,
        who,
        lab,
        project["id"],
        "Paper A",
        dataset=[DATASET_A],
        results=[RESULT_A],
        evaluation=[METRIC],
        methodology=[MODEL],
    )
    return project["id"], paper, ""


async def matrix_of(
    client: AsyncClient, who: Actor, pid: str, paper_ids: list[str]
) -> dict[str, Any]:
    resp = await _call(
        client,
        who,
        "POST",
        f"/research/projects/{pid}/matrices",
        json={"title": "Review", "paper_ids": paper_ids},
    )
    assert resp.status_code == 201, resp.text
    data: dict[str, Any] = resp.json()["data"]
    return data


def cell(data: dict[str, Any], paper_id: str, column_key: str) -> dict[str, Any]:
    col = next(c for c in data["columns"] if c["column_key"] == column_key)
    row = next(r for r in data["rows"] if r["paper"]["id"] == paper_id)
    found: dict[str, Any] = next(c for c in row["cells"] if c["column_id"] == col["id"])
    return found


class TestMatrix:
    async def test_default_columns_are_filled_from_the_analysis_with_evidence(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, lab: Harness
    ) -> None:
        pid, paper, _ = await build(client, db_session, alice, lab)
        data = await matrix_of(client, alice, pid, [paper])
        assert [c["title"] for c in data["columns"]][:3] == ["Paper title", "Authors", "Year"]
        assert len(data["columns"]) == 13 and all(c["is_default"] for c in data["columns"])
        assert cell(data, paper, "paper_title")["value"] == "Paper A"
        results = cell(data, paper, "results")
        assert results["value"] == RESULT_A["text"] and results["origin"] == "extracted"
        assert results["evidence"][0]["quote"] == "light energy into chemical"
        assert cell(data, paper, "model")["value"] == MODEL["text"]
        assert cell(data, paper, "metrics")["value"] == METRIC["text"]
        # nothing is invented for what the paper did not report
        assert cell(data, paper, "future_work")["value"] == ""

    async def test_custom_columns_rename_reorder_remove(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, lab: Harness
    ) -> None:
        pid, paper, _ = await build(client, db_session, alice, lab)
        m = await matrix_of(client, alice, pid, [paper])
        base = f"/research/matrices/{m['id']}"
        added = await _call(client, alice, "POST", f"{base}/columns", json={"title": "Ethics"})
        assert added.status_code == 201
        cols = added.json()["data"]["columns"]
        custom = cols[-1]
        assert custom["title"] == "Ethics" and custom["is_default"] is False
        dup = await _call(client, alice, "POST", f"{base}/columns", json={"title": "ethics"})
        assert dup.status_code == 409
        renamed = await _call(
            client,
            alice,
            "PATCH",
            f"{base}/columns/{custom['id']}",
            json={"title": "Ethics review"},
        )
        assert renamed.json()["data"]["columns"][-1]["title"] == "Ethics review"
        order = [custom["id"]] + [c["id"] for c in cols[:-1]]
        moved = await _call(
            client, alice, "PUT", f"{base}/columns/order", json={"column_ids": order}
        )
        assert moved.json()["data"]["columns"][0]["id"] == custom["id"]
        short = await _call(
            client, alice, "PUT", f"{base}/columns/order", json={"column_ids": order[:-1]}
        )
        assert short.status_code == 422
        gone = await _call(client, alice, "DELETE", f"{base}/columns/{custom['id']}")
        assert [c["position"] for c in gone.json()["data"]["columns"]] == list(range(13))

    async def test_researcher_edit_survives_a_refresh_and_keeps_evidence(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, lab: Harness
    ) -> None:
        pid, paper, _ = await build(client, db_session, alice, lab)
        m = await matrix_of(client, alice, pid, [paper])
        col = next(c for c in m["columns"] if c["column_key"] == "results")
        other = next(c for c in m["columns"] if c["column_key"] == "dataset")
        base = f"/research/matrices/{m['id']}"
        edited = await _call(
            client,
            alice,
            "PATCH",
            f"{base}/entries/{paper}/{col['id']}",
            json={"value": "My reading of the results"},
        )
        data = edited.json()["data"]
        mine = cell(data, paper, "results")
        assert mine["value"] == "My reading of the results" and mine["origin"] == "researcher"
        assert mine["evidence"], "the evidence link stays attached"

        # a new analysis arrives; refresh updates extracted cells only
        lab.provider.reply = (
            '{"results": {"items": [{"text": "New finding.", "origin": "reported", '
            '"confidence": 0.9, "evidence": [{"source": 1, "quote": "Photosynthesis converts"}]}]},'
            ' "dataset": {"items": [{"text": "New data.", "origin": "reported", "confidence": 0.9,'
            ' "evidence": [{"source": 1, "quote": "chloroplasts"}]}]}}'
        )
        from tests.research.test_paper_analysis import execute, start

        run = (await start(client, alice, paper)).json()["data"]
        await execute(lab, run["id"])
        fresh = (await _call(client, alice, "POST", f"{base}/refresh")).json()["data"]
        assert cell(fresh, paper, "results")["value"] == "My reading of the results"
        assert cell(fresh, paper, "dataset")["value"] == "New data."
        assert cell(fresh, paper, "dataset")["origin"] == "extracted"
        assert other["id"]

    async def test_add_and_remove_papers_and_validation(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, lab: Harness
    ) -> None:
        pid, paper, _ = await build(client, db_session, alice, lab)
        m = await matrix_of(client, alice, pid, [])
        assert m["rows"] == []
        base = f"/research/matrices/{m['id']}"
        added = await _call(client, alice, "POST", f"{base}/papers", json={"paper_ids": [paper]})
        assert len(added.json()["data"]["rows"]) == 1
        again = await _call(client, alice, "POST", f"{base}/papers", json={"paper_ids": [paper]})
        assert len(again.json()["data"]["rows"]) == 1
        assert (
            await _call(client, alice, "POST", f"{base}/papers", json={"paper_ids": [paper, paper]})
        ).status_code == 422
        assert (
            await _call(
                client, alice, "POST", f"{base}/papers", json={"paper_ids": [str(uuid.uuid4())]}
            )
        ).status_code == 404
        removed = await _call(client, alice, "DELETE", f"{base}/papers/{paper}")
        assert removed.json()["data"]["rows"] == []
        assert (await _call(client, alice, "DELETE", f"{base}/papers/{paper}")).status_code == 404

    async def test_list_patch_delete_and_archived_project(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, lab: Harness
    ) -> None:
        pid, paper, _ = await build(client, db_session, alice, lab)
        m = await matrix_of(client, alice, pid, [paper])
        listing = (await _call(client, alice, "GET", f"/research/projects/{pid}/matrices")).json()
        assert listing["total"] == 1 and listing["data"][0]["paper_count"] == 1
        renamed = await _call(
            client, alice, "PATCH", f"/research/matrices/{m['id']}", json={"title": "Renamed"}
        )
        assert renamed.json()["data"]["title"] == "Renamed"
        await _call(client, alice, "POST", f"/research/projects/{pid}/archive")
        blocked = await _call(
            client, alice, "PATCH", f"/research/matrices/{m['id']}", json={"title": "x"}
        )
        assert blocked.status_code == 409
        await _call(client, alice, "POST", f"/research/projects/{pid}/restore")
        assert (
            await _call(client, alice, "DELETE", f"/research/matrices/{m['id']}")
        ).status_code == 204
        assert (
            await _call(client, alice, "GET", f"/research/matrices/{m['id']}")
        ).status_code == 404

    async def test_deleting_a_paper_removes_its_row(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, lab: Harness
    ) -> None:
        pid, paper, _ = await build(client, db_session, alice, lab)
        m = await matrix_of(client, alice, pid, [paper])
        await _call(client, alice, "DELETE", f"/research/papers/{paper}")
        after = (await _call(client, alice, "GET", f"/research/matrices/{m['id']}")).json()["data"]
        assert after["rows"] == []


class TestOwnership:
    async def test_other_users_get_404_everywhere(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, bob: Actor, lab: Harness
    ) -> None:
        pid, paper, _ = await build(client, db_session, alice, lab)
        m = await matrix_of(client, alice, pid, [paper])
        col = m["columns"][0]["id"]
        base = f"/research/matrices/{m['id']}"
        calls: list[tuple[str, str, Any]] = [
            ("GET", f"/research/projects/{pid}/matrices", None),
            ("POST", f"/research/projects/{pid}/matrices", {"title": "x"}),
            ("GET", base, None),
            ("PATCH", base, {"title": "x"}),
            ("DELETE", base, None),
            ("POST", f"{base}/papers", {"paper_ids": [paper]}),
            ("DELETE", f"{base}/papers/{paper}", None),
            ("POST", f"{base}/columns", {"title": "x"}),
            ("PATCH", f"{base}/columns/{col}", {"title": "x"}),
            ("DELETE", f"{base}/columns/{col}", None),
            ("PUT", f"{base}/columns/order", {"column_ids": [col]}),
            ("PATCH", f"{base}/entries/{paper}/{col}", {"value": "x"}),
            ("POST", f"{base}/refresh", None),
        ]
        for method, path, body in calls:
            resp = await _call(client, bob, method, path, json=body)
            assert resp.status_code == 404, (method, path, resp.status_code)
        kept = (await _call(client, alice, "GET", base)).json()["data"]
        assert kept["title"] == "Review" and len(kept["rows"]) == 1

    async def test_papers_of_other_projects_cannot_be_added(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, lab: Harness
    ) -> None:
        pid, _, _ = await build(client, db_session, alice, lab)
        other = await make_project(client, alice)
        foreign = await analysed_paper(
            client, db_session, alice, lab, other["id"], "Paper B", results=[RESULT_A]
        )
        resp = await _call(
            client,
            alice,
            "POST",
            f"/research/projects/{pid}/matrices",
            json={"title": "x", "paper_ids": [foreign]},
        )
        assert resp.status_code == 404

    async def test_requires_authentication(self, client: AsyncClient) -> None:
        resp = await client.get(f"/api/v1/research/matrices/{uuid.uuid4()}")
        assert resp.status_code == 401
