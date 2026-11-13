"""Phase 7 M7.6: research gap candidates (engine, evidence, counter-evidence, review, access)."""

import uuid
from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.research.claims import LoadedPaper, StoredClaim
from app.research.gaps import generate_candidates
from tests.research.test_comparisons import analysed_paper
from tests.research.test_paper_analysis import claim
from tests.research.test_projects_api import make as make_project
from tests.retrieval.test_search import Actor
from tests.study.conftest import Harness
from tests.test_closeout_users_config import _call

LIMIT_DATA = claim("The dataset is small and from one site.", "inside chloroplasts", label="Gap")
LIMIT_DATA_2 = claim("Only a limited dataset was available.", "light energy", label="Gap")
ADDRESSES = claim(
    "We evaluate on multiple datasets to address generalisation.", "light energy into chemical"
)


def stored(paper: uuid.UUID, section: str, text: str, origin: str = "reported") -> StoredClaim:
    return StoredClaim(paper, section, 0, None, text, origin, None, "q", 1, None)


def loaded(title: str, *claims: StoredClaim) -> LoadedPaper:
    pid = claims[0].paper_id
    return LoadedPaper(pid, title, 2024, uuid.uuid4(), 1, list(claims))


class TestEngine:
    def test_three_papers_give_a_strong_candidate_with_safe_wording(self) -> None:
        papers = [
            loaded(f"P{i}", stored(uuid.uuid4(), "limitations", "The dataset is small."))
            for i in range(3)
        ]
        gap = next(g for g in generate_candidates(papers) if g.category == "dataset")
        assert gap.confidence_label == "strong_candidate"
        assert "Within the 3 analysed papers currently included" in gap.description
        assert "no other research exists" in gap.limitations
        assert "novel" not in (gap.description + gap.rationale).casefold()

    def test_two_papers_moderate_one_preliminary_inferred_insufficient(self) -> None:
        a, b = uuid.uuid4(), uuid.uuid4()
        two = [
            loaded("A", stored(a, "limitations", "A small dataset.")),
            loaded("B", stored(b, "future_work", "More datasets are needed.")),
        ]
        assert generate_candidates(two)[0].confidence_label == "moderate_candidate"
        one = [loaded("A", stored(a, "limitations", "A small dataset."))]
        assert generate_candidates(one)[0].confidence_label == "preliminary_candidate"
        inferred = [loaded("A", stored(a, "limitations", "A small dataset.", "ai_inferred"))]
        got = generate_candidates(inferred)[0]
        assert got.confidence_label == "insufficient_evidence"
        assert "AI-inferred" in got.limitations

    def test_counter_evidence_is_attached_and_mentioned(self) -> None:
        a, b = uuid.uuid4(), uuid.uuid4()
        papers = [
            loaded("A", stored(a, "limitations", "The dataset is small.")),
            loaded("B", stored(b, "contributions", "We release a large public dataset.")),
        ]
        gap = generate_candidates(papers)[0]
        assert len(gap.counter) == 1 and gap.counter[0].paper_id == b
        assert "read them before treating this as open" in gap.rationale

    def test_no_limitations_means_no_candidates(self) -> None:
        a = uuid.uuid4()
        assert generate_candidates([loaded("A", stored(a, "results", "Accuracy rose."))]) == []

    def test_fingerprint_is_stable(self) -> None:
        a = uuid.uuid4()
        papers = [loaded("A", stored(a, "limitations", "A small dataset."))]
        assert (
            generate_candidates(papers)[0].fingerprint == generate_candidates(papers)[0].fingerprint
        )


async def build(
    client: AsyncClient, db: AsyncSession, who: Actor, lab: Harness
) -> tuple[str, str, str]:
    project = await make_project(client, who)
    a = await analysed_paper(
        client, db, who, lab, project["id"], "Paper A", limitations=[LIMIT_DATA]
    )
    b = await analysed_paper(
        client,
        db,
        who,
        lab,
        project["id"],
        "Paper B",
        limitations=[LIMIT_DATA_2],
        contributions=[ADDRESSES],
    )
    return project["id"], a, b


async def generate(client: AsyncClient, who: Actor, pid: str, **body: Any) -> Any:
    return await _call(client, who, "POST", f"/research/projects/{pid}/gaps/generate", json=body)


class TestApi:
    async def test_generate_stores_gaps_with_evidence_and_counter_evidence(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, lab: Harness
    ) -> None:
        pid, a, b = await build(client, db_session, alice, lab)
        resp = await generate(client, alice, pid)
        assert resp.status_code == 200, resp.text
        gaps = resp.json()["data"]
        data_gap = next(g for g in gaps if g["category"] == "dataset")
        assert data_gap["confidence_label"] == "moderate_candidate"
        assert data_gap["validation_status"] == "suggested"
        roles = {e["evidence_role"] for e in data_gap["evidence"]}
        assert roles == {"supporting", "counter_evidence"}
        assert {e["research_paper_id"] for e in data_gap["evidence"]} == {a, b}
        assert all(e["research_evidence_id"] for e in data_gap["evidence"])
        assert "no other research exists" in data_gap["limitations"]
        listed = await _call(client, alice, "GET", f"/research/projects/{pid}/gaps")
        assert listed.json()["total"] == len(gaps)
        only = await _call(client, alice, "GET", f"/research/projects/{pid}/gaps?category=dataset")
        assert [g["category"] for g in only.json()["data"]] == ["dataset"]

    async def test_regeneration_replaces_untouched_and_keeps_reviewed(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, lab: Harness
    ) -> None:
        pid, _, _ = await build(client, db_session, alice, lab)
        first = (await generate(client, alice, pid)).json()["data"]
        gap = next(g for g in first if g["category"] == "dataset")
        patched = await _call(
            client,
            alice,
            "PATCH",
            f"/research/gaps/{gap['id']}",
            json={"validation_status": "accepted", "researcher_notes": "Worth pursuing"},
        )
        assert (
            patched.status_code == 200 and patched.json()["data"]["validation_status"] == "accepted"
        )
        second = (await generate(client, alice, pid)).json()["data"]
        assert all(g["category"] != "dataset" for g in second)  # not duplicated
        listed = (await _call(client, alice, "GET", f"/research/projects/{pid}/gaps")).json()
        assert listed["total"] == len(second) + 1
        accepted = await _call(
            client, alice, "GET", f"/research/projects/{pid}/gaps?status=accepted"
        )
        assert accepted.json()["total"] == 1

    async def test_edit_marks_edited_and_validates_input(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, lab: Harness
    ) -> None:
        pid, _, _ = await build(client, db_session, alice, lab)
        gap = (await generate(client, alice, pid)).json()["data"][0]
        url = f"/research/gaps/{gap['id']}"
        edited = await _call(client, alice, "PATCH", url, json={"title": "My wording"})
        assert edited.json()["data"]["edited_by_user"] is True
        assert (
            await _call(client, alice, "PATCH", url, json={"validation_status": "bogus"})
        ).status_code == 422
        assert (await _call(client, alice, "DELETE", url)).status_code == 204
        assert (await _call(client, alice, "GET", url)).status_code == 404

    async def test_needs_an_analysed_paper(
        self, client: AsyncClient, alice: Actor, lab: Harness
    ) -> None:
        project = await make_project(client, alice)
        resp = await generate(client, alice, project["id"])
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "RESEARCH_NO_ANALYSED_PAPERS"

    async def test_other_users_get_404_everywhere(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        alice: Actor,
        bob: Actor,
        lab: Harness,
    ) -> None:
        pid, a, _ = await build(client, db_session, alice, lab)
        gap = (await generate(client, alice, pid)).json()["data"][0]
        calls = [
            ("POST", f"/research/projects/{pid}/gaps/generate", {}),
            ("GET", f"/research/projects/{pid}/gaps", None),
            ("GET", f"/research/gaps/{gap['id']}", None),
            ("PATCH", f"/research/gaps/{gap['id']}", {"title": "x"}),
            ("DELETE", f"/research/gaps/{gap['id']}", None),
        ]
        for method, path, body in calls:
            resp = await _call(client, bob, method, path, json=body)
            assert resp.status_code == 404, (method, path, resp.status_code)
        mine = await _call(client, alice, "GET", f"/research/gaps/{gap['id']}")
        assert mine.status_code == 200
