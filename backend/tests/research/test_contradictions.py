"""Phase 7 M7.7: contradictions (polarity, conditions, categories, review, access)."""

import uuid
from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.research.claims import LoadedPaper, StoredClaim
from app.research.contradictions import classify, conditions_of, generate_candidates, polarity
from tests.research.test_comparisons import DATASET_A, DATASET_B, METRIC, analysed_paper
from tests.research.test_paper_analysis import claim
from tests.research.test_projects_api import make as make_project
from tests.retrieval.test_search import Actor
from tests.study.conftest import Harness
from tests.test_closeout_users_config import _call

UP = claim("Chloroplast light conversion improves energy yield.", "light energy into chemical")
DOWN = claim("Chloroplast light conversion decreases energy yield.", "light energy")


def stored(paper: uuid.UUID, section: str, text: str) -> StoredClaim:
    return StoredClaim(paper, section, 0, None, text, "reported", None, "q", 1, None)


def loaded(paper: uuid.UUID, *claims: StoredClaim) -> LoadedPaper:
    return LoadedPaper(paper, "P", 2024, uuid.uuid4(), 1, list(claims))


class TestEngine:
    def test_polarity_handles_negated_improvement(self) -> None:
        assert polarity("Accuracy improves.") == "pos"
        assert polarity("There was no improvement in accuracy.") == "neg"
        assert polarity("It improves speed but decreases accuracy.") is None
        assert polarity("A neutral statement.") is None

    def test_opposite_polarity_with_shared_terms_is_a_candidate(self) -> None:
        a, b = uuid.uuid4(), uuid.uuid4()
        papers = [
            loaded(a, stored(a, "results", "Chloroplast light conversion improves energy yield.")),
            loaded(b, stored(b, "results", "Chloroplast light conversion decreases energy yield.")),
        ]
        found = generate_candidates(papers)
        assert len(found) == 1 and "chloroplast" in found[0].shared_terms

    def test_same_polarity_or_unrelated_topics_are_not_candidates(self) -> None:
        a, b = uuid.uuid4(), uuid.uuid4()
        same = [
            loaded(a, stored(a, "results", "Chloroplast light conversion improves energy yield.")),
            loaded(b, stored(b, "results", "Chloroplast light conversion increases energy yield.")),
        ]
        assert generate_candidates(same) == []
        unrelated = [
            loaded(a, stored(a, "results", "Chloroplast light conversion improves energy yield.")),
            loaded(b, stored(b, "results", "Mitochondria oxidation decreases cellular debris.")),
        ]
        assert generate_candidates(unrelated) == []

    def test_categories(self) -> None:
        a, b = uuid.uuid4(), uuid.uuid4()

        def cat(mine: list[StoredClaim], theirs: list[StoredClaim]) -> str:
            return classify(conditions_of(loaded(a, *mine), loaded(b, *theirs)))[0]

        ds = stored(a, "dataset", "Photosynthesis data from chloroplasts.")
        ds_b = stored(b, "dataset", "Photosynthesis data from chloroplasts.")
        ds_other = stored(b, "dataset", "Krebs cycle measurements in mitochondria.")
        m = stored(a, "evaluation", "Accuracy is the metric.")
        m_b = stored(b, "evaluation", "Accuracy is the metric.")
        m_other = stored(b, "evaluation", "Latency is reported in milliseconds.")
        assert cat([stored(a, "results", "x")], [stored(b, "results", "y")]) == (
            "insufficient_evidence"
        )
        assert cat([ds, m], [ds_b, m_b]) == "genuine"
        assert cat([ds, m], [ds_other, m_b]) == "context_dependent"
        assert cat([ds, m], [ds_b, m_other]) == "metric_incompatible"


async def build(
    client: AsyncClient,
    db: AsyncSession,
    who: Actor,
    lab: Harness,
    second: dict[str, list[dict[str, Any]]],
) -> tuple[str, str, str]:
    project = await make_project(client, who)
    a = await analysed_paper(
        client,
        db,
        who,
        lab,
        project["id"],
        "Paper A",
        results=[UP],
        dataset=[DATASET_A],
        evaluation=[METRIC],
    )
    b = await analysed_paper(client, db, who, lab, project["id"], "Paper B", **second)
    return project["id"], a, b


SAME_CONDITIONS = {"results": [DOWN], "dataset": [DATASET_A], "evaluation": [METRIC]}


async def generate(client: AsyncClient, who: Actor, pid: str) -> Any:
    return await _call(
        client, who, "POST", f"/research/projects/{pid}/contradictions/generate", json={}
    )


class TestApi:
    async def test_genuine_candidate_has_both_claims_evidence_and_conditions(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, lab: Harness
    ) -> None:
        pid, a, b = await build(client, db_session, alice, lab, SAME_CONDITIONS)
        resp = await generate(client, alice, pid)
        assert resp.status_code == 200, resp.text
        rows = resp.json()["data"]
        assert len(rows) == 1
        row = rows[0]
        assert row["category"] == "genuine" and row["review_status"] == "unreviewed"
        assert {row["claim_a"]["paper_id"], row["claim_b"]["paper_id"]} == {a, b}
        for side in (row["claim_a"], row["claim_b"]):
            assert side["evidence_id"] and side["quote"] and side["paper_title"]
        assert row["conditions"]["dataset"]["comparison"] == "same"
        assert "shared_terms" in row["conditions"]

    async def test_different_datasets_are_context_dependent(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, lab: Harness
    ) -> None:
        second = {"results": [DOWN], "dataset": [DATASET_B], "evaluation": [METRIC]}
        pid, _, _ = await build(client, db_session, alice, lab, second)
        rows = (await generate(client, alice, pid)).json()["data"]
        assert [r["category"] for r in rows] == ["context_dependent"]

    async def test_review_and_regeneration_keep_reviewed_records(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, lab: Harness
    ) -> None:
        pid, _, _ = await build(client, db_session, alice, lab, SAME_CONDITIONS)
        row = (await generate(client, alice, pid)).json()["data"][0]
        url = f"/research/contradictions/{row['id']}"
        patched = await _call(
            client,
            alice,
            "PATCH",
            url,
            json={"review_status": "context_dependent", "researcher_explanation": "Other cohort"},
        )
        assert patched.status_code == 200
        assert patched.json()["data"]["review_status"] == "context_dependent"
        assert patched.json()["data"]["category"] == "genuine"  # the engine value is kept
        assert (await generate(client, alice, pid)).json()["data"] == []  # not duplicated
        listed = await _call(
            client, alice, "GET", f"/research/projects/{pid}/contradictions?review_status=dismissed"
        )
        assert listed.json()["total"] == 0
        bad = await _call(client, alice, "PATCH", url, json={"review_status": "nope"})
        assert bad.status_code == 422
        assert (await _call(client, alice, "DELETE", url)).status_code == 204

    async def test_needs_two_analysed_papers(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, lab: Harness
    ) -> None:
        project = await make_project(client, alice)
        await analysed_paper(client, db_session, alice, lab, project["id"], "Only", results=[UP])
        resp = await generate(client, alice, project["id"])
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "RESEARCH_NEED_TWO_ANALYSED_PAPERS"

    async def test_other_users_get_404_everywhere(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        alice: Actor,
        bob: Actor,
        lab: Harness,
    ) -> None:
        pid, _, _ = await build(client, db_session, alice, lab, SAME_CONDITIONS)
        row = (await generate(client, alice, pid)).json()["data"][0]
        calls: list[tuple[str, str, dict[str, Any] | None]] = [
            ("POST", f"/research/projects/{pid}/contradictions/generate", {}),
            ("GET", f"/research/projects/{pid}/contradictions", None),
            ("GET", f"/research/contradictions/{row['id']}", None),
            ("PATCH", f"/research/contradictions/{row['id']}", {"review_status": "dismissed"}),
            ("DELETE", f"/research/contradictions/{row['id']}", None),
        ]
        for method, path, body in calls:
            resp = await _call(client, bob, method, path, json=body)
            assert resp.status_code == 404, (method, path, resp.status_code)
