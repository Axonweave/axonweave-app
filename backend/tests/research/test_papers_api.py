"""Phase 7 M7.2: paper library (add, metadata, DOI, documents, duplicates, ownership)."""

import uuid
from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.research.papers import (
    InvalidDoiError,
    PaperFacts,
    candidates,
    normalise_doi,
    normalise_title,
)
from tests.research.test_projects_api import make as make_project
from tests.retrieval.test_search import Actor
from tests.study.conftest import two_docs
from tests.test_closeout_users_config import _call


async def add(client: AsyncClient, who: Actor, project_id: str, **kw: Any) -> dict[str, Any]:
    body = {"title": "Attention is all you need", **kw}
    resp = await _call(client, who, "POST", f"/research/projects/{project_id}/papers", json=body)
    assert resp.status_code == 201, resp.text
    data: dict[str, Any] = resp.json()["data"]
    return data


async def papers(client: AsyncClient, who: Actor, project_id: str, qs: str = "") -> Any:
    return await _call(client, who, "GET", f"/research/projects/{project_id}/papers{qs}")


class TestPureHelpers:
    def test_doi_normalisation(self) -> None:
        for raw in ("10.1000/ABC.1", "https://doi.org/10.1000/ABC.1", "doi: 10.1000/abc.1."):
            assert normalise_doi(raw) == "10.1000/abc.1"
        for bad in ("", "abc", "10.12/x", "https://example.com/10.1000/x"):
            try:
                normalise_doi(bad)
            except InvalidDoiError:
                continue
            raise AssertionError(bad)

    def test_duplicate_rules_are_conservative(self) -> None:
        def f(title: str, authors: list[str], year: int | None) -> PaperFacts:
            return PaperFacts(uuid.uuid4(), title, normalise_title(title), authors, year, None)

        same = [f("Deep Learning!", ["A Smith"], 2020), f("deep   learning", ["B Jones"], 2020)]
        assert [c.reason for c in candidates(same, set())] == ["same_title"]
        near = [
            f("Attention is all you need", ["Vaswani, A."], 2017),
            f("Attention is all you need.", ["Ashish Vaswani"], 2017),
        ]
        assert len(candidates(near, set())) == 1
        # similar titles alone are not enough (year and author must also agree)
        assert (
            candidates(
                [
                    f("Graph neural networks for chemistry", ["Lee"], 2019),
                    f("Graph neural networks for chemistry review", ["Kim"], 2019),
                ],
                set(),
            )
            == []
        )
        assert (
            candidates(
                [
                    f("Graph neural networks for chemistry", ["Lee"], 2019),
                    f("Graph neural networks for chemistry", ["Lee"], 2021),
                ],
                set(),
            )
            != []
        )  # identical titles still qualify for human review
        assert (
            candidates(
                [
                    f("Graph neural networks in chemistry", ["Lee"], 2019),
                    f("Graph neural networks in chemistry survey", ["Lee"], 2021),
                ],
                set(),
            )
            == []
        )
        pair = sorted(c.paper_a for c in candidates(same, set()))
        dismissed = {(sorted(p.id for p in same)[0], sorted(p.id for p in same)[1])}
        assert pair and candidates(same, dismissed) == []


class TestPapers:
    async def test_add_manual_paper_and_edit_metadata(
        self, client: AsyncClient, alice: Actor
    ) -> None:
        proj = await make_project(client, alice)
        p = await add(
            client,
            alice,
            proj["id"],
            authors=["Ashish Vaswani", " Ashish Vaswani ", "Noam Shazeer"],
            publication_year=2017,
            venue="NeurIPS",
            doi="https://doi.org/10.5555/3295222.3295349",
            keywords=["transformer"],
        )
        assert p["metadata_source"] == "user_supplied" and p["metadata_verified"] is False
        assert p["doi"] == "10.5555/3295222.3295349"
        assert p["url"] == "https://doi.org/10.5555/3295222.3295349"
        assert p["authors"] == ["Ashish Vaswani", "Noam Shazeer"]
        assert p["analysis_status"] == "not_analysed" and p["processing_status"] is None
        upd = await _call(
            client,
            alice,
            "PATCH",
            f"/research/papers/{p['id']}",
            json={"publisher": "Curran", "metadata_verified": True, "venue": None},
        )
        assert upd.status_code == 200
        data = upd.json()["data"]
        assert data["publisher"] == "Curran" and data["venue"] is None
        assert data["metadata_verified"] is True and data["authors"] == p["authors"]
        # editing metadata afterwards clears the verified flag unless re-sent
        again = await _call(
            client, alice, "PATCH", f"/research/papers/{p['id']}", json={"venue": "NIPS"}
        )
        assert again.json()["data"]["metadata_verified"] is False
        project = (await _call(client, alice, "GET", f"/research/projects/{proj['id']}")).json()
        assert project["data"]["paper_count"] == 1

    async def test_validation(self, client: AsyncClient, alice: Actor) -> None:
        proj = await make_project(client, alice)
        url = f"/research/projects/{proj['id']}/papers"
        bad = [
            {"title": "x"},
            {"title": "Fine title", "doi": "not-a-doi"},
            {"title": "Fine title", "url": "javascript:alert(1)"},
            {"title": "Fine title", "publication_year": 12},
            {"title": "Fine title", "metadata_source": "external_provider"},
            {"title": "Fine title", "status": "maybe"},
        ]
        for body in bad:
            assert (await _call(client, alice, "POST", url, json=body)).status_code == 422, body

    async def test_duplicate_doi_is_refused_not_merged(
        self, client: AsyncClient, alice: Actor
    ) -> None:
        proj = await make_project(client, alice)
        await add(client, alice, proj["id"], doi="10.1000/abc")
        resp = await _call(
            client,
            alice,
            "POST",
            f"/research/projects/{proj['id']}/papers",
            json={"title": "Same work again", "doi": "DOI:10.1000/ABC"},
        )
        assert resp.status_code == 409 and resp.json()["error"]["code"] == "RESEARCH_DUPLICATE_DOI"
        # the same DOI in another project is a different library entry
        other = await make_project(client, alice, title="Second project")
        await add(client, alice, other["id"], doi="10.1000/abc")

    async def test_link_existing_document(
        self, client: AsyncClient, alice: Actor, db_session: AsyncSession
    ) -> None:
        proj = await make_project(client, alice)
        doc = await two_docs(db_session, alice, "Paper PDF")
        p = await add(client, alice, proj["id"], document_id=str(doc.id))
        assert p["document_id"] == str(doc.id) and p["document_name"]
        assert p["processing_status"] is not None  # the Phase 3 status of the file
        clash = await _call(
            client,
            alice,
            "POST",
            f"/research/projects/{proj['id']}/papers",
            json={"title": "Another record", "document_id": str(doc.id)},
        )
        assert clash.status_code == 409
        has_file = (await papers(client, alice, proj["id"], "?has_file=true")).json()
        assert has_file["total"] == 1
        # deleting the library record leaves the document alone
        assert (
            await _call(client, alice, "DELETE", f"/research/papers/{p['id']}")
        ).status_code == 204
        assert await db_session.get(Document, doc.id) is not None

    async def test_list_search_filter_sort(self, client: AsyncClient, alice: Actor) -> None:
        proj = await make_project(client, alice)
        await add(
            client,
            alice,
            proj["id"],
            title="Alpha networks",
            publication_year=2018,
            authors=["Rivera"],
        )
        await add(
            client, alice, proj["id"], title="Beta methods", publication_year=2020, status="read"
        )
        await add(client, alice, proj["id"], title="Gamma survey", venue="Nature")
        listed = (await papers(client, alice, proj["id"], "?sort_by=title&sort_dir=asc")).json()
        assert [x["title"] for x in listed["data"]] == [
            "Alpha networks",
            "Beta methods",
            "Gamma survey",
        ]
        assert (await papers(client, alice, proj["id"], "?q=rivera")).json()["total"] == 1
        assert (await papers(client, alice, proj["id"], "?q=nature")).json()["total"] == 1
        assert (await papers(client, alice, proj["id"], "?year=2020")).json()["total"] == 1
        assert (await papers(client, alice, proj["id"], "?status=read")).json()["total"] == 1
        assert (await papers(client, alice, proj["id"], "?q=%25")).json()["total"] == 0
        for bad in ("limit=101", "sort_by=doi", "status=nope", "year=5"):
            assert (await papers(client, alice, proj["id"], f"?{bad}")).status_code == 422

    async def test_archive_restore_delete(self, client: AsyncClient, alice: Actor) -> None:
        proj = await make_project(client, alice)
        p = await add(client, alice, proj["id"])
        url = f"/research/papers/{p['id']}"
        assert (await _call(client, alice, "POST", f"{url}/restore")).status_code == 409
        assert (await _call(client, alice, "POST", f"{url}/archive")).status_code == 200
        assert (await papers(client, alice, proj["id"])).json()["total"] == 0
        assert (await papers(client, alice, proj["id"], "?archived=true")).json()["total"] == 1
        edit = await _call(client, alice, "PATCH", url, json={"title": "Changed title"})
        assert edit.status_code == 409
        assert (await _call(client, alice, "POST", f"{url}/restore")).status_code == 200
        assert (await _call(client, alice, "DELETE", url)).status_code == 204
        assert (await _call(client, alice, "GET", url)).status_code == 404


class TestDuplicateReview:
    async def _pair(
        self, client: AsyncClient, who: Actor
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        proj = await make_project(client, who)
        a = await add(
            client,
            who,
            proj["id"],
            title="Deep learning",
            authors=["LeCun"],
            publication_year=2015,
            venue="Nature",
        )
        b = await add(
            client,
            who,
            proj["id"],
            title="Deep Learning.",
            authors=["Y. LeCun"],
            publication_year=2015,
            doi="10.1038/nature14539",
            keywords=["cnn"],
        )
        return proj, a, b

    async def test_candidates_then_not_duplicate_decision_sticks(
        self, client: AsyncClient, alice: Actor
    ) -> None:
        proj, a, b = await self._pair(client, alice)
        await add(client, alice, proj["id"], title="Unrelated topic", publication_year=2001)
        found = (
            await _call(client, alice, "GET", f"/research/projects/{proj['id']}/papers/duplicates")
        ).json()["data"]
        assert len(found) == 1 and found[0]["reason"] == "same_title"
        assert {found[0]["paper_a"]["id"], found[0]["paper_b"]["id"]} == {a["id"], b["id"]}
        # nothing was merged automatically
        assert (await papers(client, alice, proj["id"])).json()["total"] == 3
        res = await _call(
            client,
            alice,
            "POST",
            f"/research/projects/{proj['id']}/papers/duplicates/resolve",
            json={"paper_id": a["id"], "other_id": b["id"], "action": "not_duplicate"},
        )
        assert res.status_code == 200
        after = (
            await _call(client, alice, "GET", f"/research/projects/{proj['id']}/papers/duplicates")
        ).json()["data"]
        assert after == []
        assert (await papers(client, alice, proj["id"])).json()["total"] == 3

    async def test_merge_keeps_survivor_values_and_fills_gaps(
        self, client: AsyncClient, alice: Actor
    ) -> None:
        proj, a, b = await self._pair(client, alice)
        res = await _call(
            client,
            alice,
            "POST",
            f"/research/projects/{proj['id']}/papers/duplicates/resolve",
            json={
                "paper_id": a["id"],
                "other_id": b["id"],
                "action": "merge",
                "survivor_id": a["id"],
            },
        )
        assert res.status_code == 200, res.text
        s = res.json()["data"]["survivor"]
        assert s["id"] == a["id"] and s["venue"] == "Nature"  # survivor value kept
        assert s["doi"] == "10.1038/nature14539" and s["keywords"] == ["cnn"]  # gaps filled
        assert (await _call(client, alice, "GET", f"/research/papers/{b['id']}")).status_code == 404
        assert (await papers(client, alice, proj["id"])).json()["total"] == 1

    async def test_merge_needs_a_valid_survivor(self, client: AsyncClient, alice: Actor) -> None:
        proj, a, b = await self._pair(client, alice)
        url = f"/research/projects/{proj['id']}/papers/duplicates/resolve"
        for body in (
            {"paper_id": a["id"], "other_id": b["id"], "action": "merge"},
            {
                "paper_id": a["id"],
                "other_id": b["id"],
                "action": "merge",
                "survivor_id": str(uuid.uuid4()),
            },
            {"paper_id": a["id"], "other_id": a["id"], "action": "not_duplicate"},
        ):
            assert (await _call(client, alice, "POST", url, json=body)).status_code == 422
        assert (await papers(client, alice, proj["id"])).json()["total"] == 2


class TestOwnership:
    async def test_other_users_cannot_touch_papers(
        self, client: AsyncClient, alice: Actor, bob: Actor, db_session: AsyncSession
    ) -> None:
        proj = await make_project(client, alice)
        p = await add(client, alice, proj["id"])
        pid, url = proj["id"], f"/research/papers/{p['id']}"
        assert (await _call(client, bob, "GET", url)).status_code == 404
        assert (
            await _call(client, bob, "PATCH", url, json={"title": "Hijacked title"})
        ).status_code == 404
        assert (await _call(client, bob, "POST", f"{url}/archive")).status_code == 404
        assert (await _call(client, bob, "DELETE", url)).status_code == 404
        assert (await papers(client, bob, pid)).status_code == 404
        resp = await _call(
            client,
            bob,
            "POST",
            f"/research/projects/{pid}/papers",
            json={"title": "Intruder paper"},
        )
        assert resp.status_code == 404
        dup = f"/research/projects/{pid}/papers/duplicates"
        assert (await _call(client, bob, "GET", dup)).status_code == 404
        res = await _call(
            client,
            bob,
            "POST",
            f"{dup}/resolve",
            json={"paper_id": p["id"], "other_id": str(uuid.uuid4()), "action": "not_duplicate"},
        )
        assert res.status_code == 404
        # a foreign document cannot be attached, even to bob's own project
        bob_proj = await make_project(client, bob, title="Bob project")
        doc = await two_docs(db_session, alice, "Alice PDF")
        steal = await _call(
            client,
            bob,
            "POST",
            f"/research/projects/{bob_proj['id']}/papers",
            json={"title": "Stolen file", "document_id": str(doc.id)},
        )
        assert steal.status_code == 404
        still = (await _call(client, alice, "GET", url)).json()["data"]
        assert still["title"] == "Attention is all you need"

    async def test_requires_authentication(self, client: AsyncClient) -> None:
        pid = uuid.uuid4()
        assert (await client.get(f"/api/v1/research/projects/{pid}/papers")).status_code == 401
        assert (await client.get(f"/api/v1/research/papers/{pid}")).status_code == 401
