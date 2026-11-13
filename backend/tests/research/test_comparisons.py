"""Phase 7 M7.4: comparing papers (evidence, missing information, comparability, saving, access).

Papers are analysed with the FakeProvider's scripted JSON, then compared; the comparison itself
makes no model call."""

import uuid
from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.research.comparison import ClaimInput, PaperInput, build_comparison, terms_of
from tests.research.test_paper_analysis import (  # noqa: F401  (fixture + helpers)
    claim,
    execute,
    reply,
    start,
)
from tests.research.test_projects_api import make as make_project
from tests.retrieval.test_search import Actor
from tests.study.conftest import Harness, two_docs
from tests.test_closeout_users_config import _call

DATASET_A = claim("Photosynthesis data from chloroplasts.", "inside chloroplasts", label="Dataset")
DATASET_B = claim(
    "Krebs cycle measurements in mitochondria.", "acetyl-CoA to carbon dioxide", 2, label="Dataset"
)
METRIC = claim("Accuracy is the metric.", "light energy", label="Metric")
RESULT_A = claim("Chloroplasts turn light into chemical energy.", "light energy into chemical")
RESULT_B = claim("Mitochondria oxidise acetyl-CoA.", "Krebs cycle oxidises", 2)


async def analysed_paper(
    client: AsyncClient,
    db: AsyncSession,
    who: Actor,
    lab: Harness,
    project_id: str,
    title: str,
    **sections: list[dict[str, Any]],
) -> str:
    doc = await two_docs(db, who)
    made = await _call(
        client,
        who,
        "POST",
        f"/research/projects/{project_id}/papers",
        json={"title": title, "document_id": str(doc.id)},
    )
    assert made.status_code == 201, made.text
    paper_id: str = made.json()["data"]["id"]
    lab.provider.reply = reply(**sections)
    run = (await start(client, who, paper_id)).json()["data"]
    assert await execute(lab, run["id"]) == "completed"
    return paper_id


async def compare(
    client: AsyncClient, who: Actor, project_id: str, paper_ids: list[str], **extra: Any
) -> Any:
    return await _call(
        client,
        who,
        "POST",
        f"/research/projects/{project_id}/comparisons",
        json={"title": "A vs B", "paper_ids": paper_ids, **extra},
    )


def row(data: dict[str, Any], key: str) -> dict[str, Any]:
    found: dict[str, Any] = next(r for r in data["result"]["rows"] if r["dimension"] == key)
    return found


class TestEngine:
    def paper(self, pid: str, **claims: list[str]) -> PaperInput:
        return PaperInput(
            pid,
            pid,
            "x",
            1,
            {
                s: [ClaimInput(t, None, "reported", []) for t in texts]
                for s, texts in claims.items()
            },
        )

    def test_terms_ignore_filler_and_keep_numbers(self) -> None:
        assert terms_of("The accuracy was 95 percent with this approach") == {
            "accuracy",
            "95",
            "percent",
        }

    def test_nothing_reported_is_never_filled_in(self) -> None:
        out = build_comparison([self.paper("a"), self.paper("b")])
        assert all(r["status"] == "not_reported" for r in out["rows"])
        assert all(not c["items"] for r in out["rows"] for c in r["cells"])
        assert out["comparability"]["results_directly_comparable"] is False

    def test_missing_in_one_paper_gives_no_similarities(self) -> None:
        out = build_comparison(
            [self.paper("a", dataset=["imagenet photos"]), self.paper("b")], ["dataset"]
        )
        only = out["rows"][0]
        assert only["status"] == "partial" and only["similarities"] == []
        assert only["not_reported_for"] == ["b"]
        assert out["comparability"]["dataset"] == "unknown"


class TestComparisons:
    async def two_papers(
        self,
        client: AsyncClient,
        db: AsyncSession,
        who: Actor,
        lab: Harness,
        a: dict[str, list[dict[str, Any]]],
        b: dict[str, list[dict[str, Any]]],
    ) -> tuple[str, str, str]:
        project = await make_project(client, who)
        one = await analysed_paper(client, db, who, lab, project["id"], "Paper A", **a)
        two = await analysed_paper(client, db, who, lab, project["id"], "Paper B", **b)
        return project["id"], one, two

    async def test_different_datasets_are_flagged_and_results_not_comparable(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, lab: Harness
    ) -> None:
        pid, one, two = await self.two_papers(
            client,
            db_session,
            alice,
            lab,
            {"dataset": [DATASET_A], "results": [RESULT_A], "evaluation": [METRIC]},
            {"dataset": [DATASET_B], "results": [RESULT_B], "evaluation": [METRIC]},
        )
        resp = await compare(client, alice, pid, [one, two])
        assert resp.status_code == 201, resp.text
        data = resp.json()["data"]
        comp = data["result"]["comparability"]
        assert comp["dataset"] == "different" and comp["results_directly_comparable"] is False
        assert any("different datasets" in w for w in comp["warnings"])
        assert row(data, "results")["directly_comparable"] is False
        # evidence is attached to the compared claims
        cell = row(data, "results")["cells"][0]
        assert cell["items"][0]["evidence"][0]["quote"] == "light energy into chemical"
        # every dimension is present; unreported ones say so instead of being filled in
        assert len(data["result"]["rows"]) == 12
        assert row(data, "future_work")["status"] == "not_reported"
        assert [p["title"] for p in data["result"]["papers"]] == ["Paper A", "Paper B"]
        assert data["paper_ids"] == [one, two]

    async def test_same_dataset_and_metrics_can_be_compared(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, lab: Harness
    ) -> None:
        shared = {"dataset": [DATASET_A], "evaluation": [METRIC]}
        pid, one, two = await self.two_papers(
            client,
            db_session,
            alice,
            lab,
            {**shared, "results": [RESULT_A]},
            {**shared, "results": [RESULT_B]},
        )
        data = (await compare(client, alice, pid, [one, two])).json()["data"]
        comp = data["result"]["comparability"]
        assert comp["dataset"] == "similar" and comp["metrics"] == "similar"
        assert comp["results_directly_comparable"] is True
        assert "chloroplasts" in row(data, "dataset")["similarities"]

    async def test_missing_information_is_unconfirmed_not_comparable(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, lab: Harness
    ) -> None:
        pid, one, two = await self.two_papers(
            client,
            db_session,
            alice,
            lab,
            {"dataset": [DATASET_A], "results": [RESULT_A]},
            {"results": [RESULT_B]},
        )
        data = (await compare(client, alice, pid, [one, two])).json()["data"]
        assert row(data, "dataset")["status"] == "partial"
        assert row(data, "dataset")["not_reported_for"] == [two]
        assert data["result"]["comparability"]["dataset"] == "unknown"
        assert data["result"]["comparability"]["results_directly_comparable"] is False

    async def test_dimension_subset(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, lab: Harness
    ) -> None:
        pid, one, two = await self.two_papers(
            client, db_session, alice, lab, {"results": [RESULT_A]}, {"results": [RESULT_B]}
        )
        data = (
            await compare(client, alice, pid, [one, two], dimensions=["results", "dataset"])
        ).json()["data"]
        assert [r["dimension"] for r in data["result"]["rows"]] == ["dataset", "results"]

    async def test_input_rules(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, lab: Harness
    ) -> None:
        pid, one, two = await self.two_papers(
            client, db_session, alice, lab, {"results": [RESULT_A]}, {"results": [RESULT_B]}
        )
        assert (await compare(client, alice, pid, [one])).status_code == 422
        assert (await compare(client, alice, pid, [one, one])).status_code == 422
        assert (
            await compare(client, alice, pid, [one, two], dimensions=["nonsense"])
        ).status_code == 422
        # a paper with no completed analysis cannot be compared
        bare = await _call(
            client, alice, "POST", f"/research/projects/{pid}/papers", json={"title": "Bare"}
        )
        resp = await compare(client, alice, pid, [one, bare.json()["data"]["id"]])
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "RESEARCH_PAPER_NOT_ANALYSED"

    async def test_saved_comparison_survives_reanalysis_and_notes_do_not_change_claims(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, lab: Harness
    ) -> None:
        pid, one, two = await self.two_papers(
            client, db_session, alice, lab, {"results": [RESULT_A]}, {"results": [RESULT_B]}
        )
        made = (await compare(client, alice, pid, [one, two])).json()["data"]
        listing = (
            await _call(client, alice, "GET", f"/research/projects/{pid}/comparisons")
        ).json()
        assert listing["total"] == 1 and listing["data"][0]["paper_count"] == 2

        lab.provider.reply = reply(results=[claim("A different finding.", "Krebs cycle", 2)])
        rerun = (await start(client, alice, one)).json()["data"]
        await execute(lab, rerun["id"])
        again = (await _call(client, alice, "GET", f"/research/comparisons/{made['id']}")).json()[
            "data"
        ]
        assert again["result"] == made["result"]  # a snapshot: later analyses do not rewrite it

        edited = await _call(
            client,
            alice,
            "PATCH",
            f"/research/comparisons/{made['id']}",
            json={"title": "Renamed", "notes": {"results": "Check the sample", "dataset": ""}},
        )
        body = edited.json()["data"]
        assert body["title"] == "Renamed" and body["notes"] == {"results": "Check the sample"}
        assert body["result"] == made["result"]
        bad = await _call(
            client,
            alice,
            "PATCH",
            f"/research/comparisons/{made['id']}",
            json={"result": {"rows": []}},
        )
        assert bad.status_code == 422

        gone = await _call(client, alice, "DELETE", f"/research/comparisons/{made['id']}")
        assert gone.status_code == 204
        assert (
            await _call(client, alice, "GET", f"/research/comparisons/{made['id']}")
        ).status_code == 404

    async def test_archived_project_is_refused(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, lab: Harness
    ) -> None:
        pid, one, two = await self.two_papers(
            client, db_session, alice, lab, {"results": [RESULT_A]}, {"results": [RESULT_B]}
        )
        await _call(client, alice, "POST", f"/research/projects/{pid}/archive")
        resp = await compare(client, alice, pid, [one, two])
        assert resp.status_code == 409


class TestOwnership:
    async def test_other_users_get_404_and_cannot_use_foreign_papers(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        alice: Actor,
        bob: Actor,
        lab: Harness,
    ) -> None:
        project = await make_project(client, alice)
        one = await analysed_paper(
            client, db_session, alice, lab, project["id"], "Paper A", results=[RESULT_A]
        )
        two = await analysed_paper(
            client, db_session, alice, lab, project["id"], "Paper B", results=[RESULT_B]
        )
        made = (await compare(client, alice, project["id"], [one, two])).json()["data"]

        assert (await compare(client, bob, project["id"], [one, two])).status_code == 404
        for method, path, body in [
            ("GET", f"/research/projects/{project['id']}/comparisons", None),
            ("GET", f"/research/comparisons/{made['id']}", None),
            ("PATCH", f"/research/comparisons/{made['id']}", {"title": "hijack"}),
            ("DELETE", f"/research/comparisons/{made['id']}", None),
        ]:
            resp = await _call(client, bob, method, path, json=body)
            assert resp.status_code == 404, (method, path)
        # bob's own project cannot pull in alice's papers
        mine = await make_project(client, bob)
        assert (await compare(client, bob, mine["id"], [one, two])).status_code == 404
        # alice's comparison is untouched
        kept = (await _call(client, alice, "GET", f"/research/comparisons/{made['id']}")).json()
        assert kept["data"]["title"] == "A vs B"

    async def test_papers_from_another_project_are_not_found(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, lab: Harness
    ) -> None:
        p1 = await make_project(client, alice)
        p2 = await make_project(client, alice)
        one = await analysed_paper(
            client, db_session, alice, lab, p1["id"], "Paper A", results=[RESULT_A]
        )
        two = await analysed_paper(
            client, db_session, alice, lab, p2["id"], "Paper B", results=[RESULT_B]
        )
        assert (await compare(client, alice, p1["id"], [one, two])).status_code == 404

    async def test_requires_authentication(self, client: AsyncClient) -> None:
        resp = await client.get(f"/api/v1/research/comparisons/{uuid.uuid4()}")
        assert resp.status_code == 401
