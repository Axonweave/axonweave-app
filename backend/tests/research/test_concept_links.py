"""Phase 7 M7.10: links between analysed papers and existing knowledge nodes."""

import uuid
from typing import Any

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeNode
from app.models.learner import LearnerConceptState, LearnerEvidence
from app.research.claims import LoadedPaper, StoredClaim
from app.research.concept_links import NodeNames, find_mentions
from tests.knowledge.test_graph_api import node
from tests.research.test_comparisons import DATASET_A, RESULT_A, analysed_paper
from tests.research.test_projects_api import make as make_project
from tests.retrieval.test_search import Actor
from tests.study.conftest import Harness
from tests.test_closeout_users_config import _call

PID = uuid.UUID("11111111-1111-1111-1111-111111111111")


def claim(text: str, *, evidence: bool = True, section: str = "results") -> StoredClaim:
    ev = uuid.uuid4() if evidence else None
    return StoredClaim(PID, section, 0, None, text, "reported", ev, "q", 1, None)


def paper(*claims: StoredClaim) -> LoadedPaper:
    return LoadedPaper(PID, "Paper", 2020, uuid.uuid4(), 1, list(claims))


class TestEngine:
    def test_matches_whole_phrases_by_name_and_alias(self) -> None:
        n1, n2, n3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        nodes = [
            NodeNames(n1, "Chemical energy"),
            NodeNames(n2, "Cell", ("cellular respiration",)),
            NodeNames(n3, "Krebs cycle"),
        ]
        p = paper(claim("Chloroplasts store chemical energy."), claim("Cellular respiration runs."))
        found = {m.node_id: m for m in find_mentions([p], nodes)}
        assert set(found) == {n1, n2}  # "Cell" alone does not match "Cellular"
        assert found[n1].match_kind == "name" and found[n2].match_kind == "alias"
        assert found[n2].matched_text == "cellular respiration"

    def test_short_names_are_ignored_and_evidence_backed_claims_are_preferred(self) -> None:
        n1, n2 = uuid.uuid4(), uuid.uuid4()
        p = paper(
            claim("The ATP pool grows.", evidence=False),
            claim("The ATP pool is measured again.", evidence=True),
        )
        found = find_mentions([p], [NodeNames(n1, "ATP pool"), NodeNames(n2, "DB")])
        assert [m.node_id for m in found] == [n1]
        assert found[0].claim.evidence_id is not None and found[0].mention_count == 2

    def test_references_are_not_searched(self) -> None:
        n1 = uuid.uuid4()
        p = paper(claim("Krebs cycle review", section="references"))
        assert find_mentions([p], [NodeNames(n1, "Krebs cycle")]) == []


async def build(client: AsyncClient, db: AsyncSession, who: Actor, lab: Harness) -> tuple[str, str]:
    project = await make_project(client, who)
    paper_id = await analysed_paper(
        client, db, who, lab, project["id"], "Paper A", results=[RESULT_A], dataset=[DATASET_A]
    )
    return project["id"], paper_id


async def suggest(client: AsyncClient, who: Actor, pid: str) -> Any:
    return await _call(
        client, who, "POST", f"/research/projects/{pid}/concept-links/suggest", json={}
    )


class TestApi:
    async def test_suggest_confirm_and_navigate(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, lab: Harness
    ) -> None:
        pid, paper_id = await build(client, db_session, alice, lab)
        chloro = await node(client, alice, "Chloroplasts")
        energy = await node(client, alice, "Energy conversion", aliases=["chemical energy"])
        await node(client, alice, "Krebs cycle")
        resp = await suggest(client, alice, pid)
        assert resp.status_code == 200, resp.text
        links = {link["node"]["name"]: link for link in resp.json()["data"]}
        assert set(links) == {"Chloroplasts", "Energy conversion"}
        link = links["Chloroplasts"]
        assert link["link_status"] == "suggested" and link["match_kind"] == "name"
        assert link["claim_text"] and link["evidence_id"] and link["paper"]["id"] == paper_id
        assert links["Energy conversion"]["match_kind"] == "alias"
        # suggested links show the paper, but findings come only from confirmed ones
        research = (
            await _call(client, alice, "GET", f"/research/concepts/{chloro['id']}/research")
        ).json()["data"]
        assert [p["link_status"] for p in research["papers"]] == ["suggested"]
        assert research["findings"] == [] and research["datasets"] == []
        confirmed = await _call(
            client,
            alice,
            "PATCH",
            f"/research/concept-links/{link['id']}",
            json={"link_status": "confirmed"},
        )
        assert confirmed.json()["data"]["link_status"] == "confirmed"
        research = (
            await _call(client, alice, "GET", f"/research/concepts/{chloro['id']}/research")
        ).json()["data"]
        assert research["node"]["name"] == "Chloroplasts"
        assert [p["link_status"] for p in research["papers"]] == ["confirmed"]
        assert (
            research["findings"][0]["claim_text"] == RESULT_A["text"]
            and research["findings"][0]["quote"]
        )
        assert research["datasets"][0]["paper_id"] == paper_id and research["gaps"] == []
        by_paper = (
            await _call(client, alice, "GET", f"/research/papers/{paper_id}/concepts")
        ).json()["data"]
        assert {c["node"]["id"] for c in by_paper} == {chloro["id"], energy["id"]}

    async def test_decisions_are_never_reset_and_rejected_links_are_hidden(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, lab: Harness
    ) -> None:
        pid, paper_id = await build(client, db_session, alice, lab)
        await node(client, alice, "Chloroplasts")
        first = (await suggest(client, alice, pid)).json()["data"]
        link_id = first[0]["id"]
        await _call(
            client,
            alice,
            "PATCH",
            f"/research/concept-links/{link_id}",
            json={"link_status": "rejected"},
        )
        again = (await suggest(client, alice, pid)).json()["data"]
        assert again == []  # a rejected pair is not suggested again
        listed = (
            await _call(
                client, alice, "GET", f"/research/projects/{pid}/concept-links?link_status=rejected"
            )
        ).json()
        assert listed["total"] == 1
        hidden = (
            await _call(client, alice, "GET", f"/research/papers/{paper_id}/concepts")
        ).json()["data"]
        assert hidden == []
        assert (
            await _call(client, alice, "DELETE", f"/research/concept-links/{link_id}")
        ).status_code == 204
        bad = await _call(
            client, alice, "PATCH", f"/research/concept-links/{link_id}", json={"link_status": "x"}
        )
        assert bad.status_code in (404, 422)

    async def test_nothing_is_created_in_the_graph_or_the_learner_tables(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, lab: Harness
    ) -> None:
        pid, _ = await build(client, db_session, alice, lab)
        await node(client, alice, "Chloroplasts")

        async def counts() -> list[int]:
            out: list[int] = []
            for table in (KnowledgeNode, LearnerConceptState, LearnerEvidence):
                total = (await db_session.execute(select(func.count(table.id)))).scalar_one()
                out.append(int(total))
            return out

        before = await counts()
        link = (await suggest(client, alice, pid)).json()["data"][0]
        await _call(
            client,
            alice,
            "PATCH",
            f"/research/concept-links/{link['id']}",
            json={"link_status": "confirmed"},
        )
        assert await counts() == before

    async def test_needs_an_analysed_paper_and_ignores_other_users_nodes(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, bob: Actor, lab: Harness
    ) -> None:
        empty = await make_project(client, alice)
        resp = await suggest(client, alice, empty["id"])
        assert (
            resp.status_code == 422
            and resp.json()["error"]["code"] == "RESEARCH_NO_ANALYSED_PAPERS"
        )
        pid, _ = await build(client, db_session, alice, lab)
        await node(client, bob, "Chloroplasts")  # same name, another user's graph
        assert (await suggest(client, alice, pid)).json()["data"] == []

    async def test_other_users_get_404_everywhere(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, bob: Actor, lab: Harness
    ) -> None:
        pid, paper_id = await build(client, db_session, alice, lab)
        chloro = await node(client, alice, "Chloroplasts")
        link = (await suggest(client, alice, pid)).json()["data"][0]
        calls: list[tuple[str, str, dict[str, Any] | None]] = [
            ("POST", f"/research/projects/{pid}/concept-links/suggest", {}),
            ("GET", f"/research/projects/{pid}/concept-links", None),
            ("PATCH", f"/research/concept-links/{link['id']}", {"link_status": "confirmed"}),
            ("DELETE", f"/research/concept-links/{link['id']}", None),
            ("GET", f"/research/papers/{paper_id}/concepts", None),
            ("GET", f"/research/concepts/{chloro['id']}/research", None),
        ]
        for method, path, body in calls:
            resp = await _call(client, bob, method, path, json=body)
            assert resp.status_code == 404, (method, path, resp.status_code)
