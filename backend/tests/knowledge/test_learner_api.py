"""Phase 6 M6.10: evidence, mastery states, recommendations, dashboard and the full flow
(quiz -> evidence -> mapping -> mastery -> recommendations -> dashboard), with isolation checks."""

from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.knowledge.test_graph_api import edge, node
from tests.retrieval.test_search import Actor
from tests.study.conftest import Harness
from tests.study.test_quiz_assessment import new_quiz, run_attempt
from tests.test_closeout_users_config import _call


async def get(client: AsyncClient, who: Actor, path: str) -> Any:
    resp = await _call(client, who, "GET", path)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def post(client: AsyncClient, who: Actor, path: str, **kw: Any) -> Any:
    return await _call(client, who, "POST", path, **kw)


async def wrong_quiz_with_concepts(
    client: AsyncClient, study: Harness, who: Actor, db: AsyncSession
) -> dict[str, dict[str, Any]]:
    """Two concepts matching the quiz topics, two failed attempts, evidence synced."""
    krebs = await node(client, who, "Krebs cycle")
    photo = await node(client, who, "Photosynthesis")
    other = await node(client, who, "Unrelated idea")
    assert (await edge(client, who, krebs["id"], photo["id"], "PREREQUISITE_OF")).status_code == 201
    assert (await edge(client, who, other["id"], photo["id"])).status_code == 201
    for _ in range(2):
        quiz_id, t = await new_quiz(client, study, who, db)
        await run_attempt(client, who, quiz_id, t, right=False)
    resp = await post(client, who, "/knowledge/learner/sync")
    assert resp.status_code == 200, resp.text
    return {"krebs": krebs, "photo": photo, "other": other}


class TestEvidenceAndMastery:
    async def test_sync_maps_exact_topics_and_is_idempotent(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        c = await wrong_quiz_with_concepts(client, study, alice, db_session)
        first = (await get(client, alice, "/knowledge/learner/summary"))["data"]
        assert first["total"] > 0
        again = (await post(client, alice, "/knowledge/learner/sync")).json()["data"]
        assert again["ingested"] == 0  # event deduplication
        assert (await get(client, alice, "/knowledge/learner/summary"))["data"]["total"] == first[
            "total"
        ]
        ev = await get(client, alice, f"/knowledge/learner/evidence?node_id={c['krebs']['id']}")
        assert ev["total"] >= 1
        assert all("question" not in e and "answer" not in e for e in ev["data"])

    async def test_states_are_explained_and_unassessed_has_no_score(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        c = await wrong_quiz_with_concepts(client, study, alice, db_session)
        none = (await get(client, alice, f"/knowledge/learner/states/{c['other']['id']}"))["data"]
        assert none["state"] == "NOT_ASSESSED" and none["mastery_estimate"] is None
        st = (await get(client, alice, f"/knowledge/learner/states/{c['krebs']['id']}"))["data"]
        assert st["evidence_count"] >= 1 and st["explanation"]
        assert st["state"] != "STRONG"
        listed = await get(client, alice, "/knowledge/learner/states")
        assert listed["total"] >= 1

    async def test_recalculate_is_reproducible(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        c = await wrong_quiz_with_concepts(client, study, alice, db_session)
        path = f"/knowledge/learner/states/{c['krebs']['id']}"
        before = (await get(client, alice, path))["data"]
        assert (await post(client, alice, "/knowledge/learner/recalculate")).status_code == 202
        after = (await get(client, alice, path))["data"]
        assert (before["mastery_estimate"], before["state"]) == (
            after["mastery_estimate"],
            after["state"],
        )

    async def test_detection_needs_enough_evidence(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        c = await wrong_quiz_with_concepts(client, study, alice, db_session)
        resp = await post(
            client,
            alice,
            "/knowledge/learner/misconceptions/detect",
            json={"node_id": c["other"]["id"]},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["outcome"] == "insufficient_evidence" and data["misconceptions"] == []


class TestRecommendationsAndDashboard:
    async def test_full_flow(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        c = await wrong_quiz_with_concepts(client, study, alice, db_session)
        recs = (await get(client, alice, "/recommendations/learner"))["data"]["items"]
        assert recs, "weak evidence should produce a recommendation"
        for r in recs:
            assert r["reason"] and r["suggested_action"] and r["evidence"]["rule"]
        assert [r["score"] for r in recs] == sorted((r["score"] for r in recs), reverse=True)

        dash = (await get(client, alice, "/knowledge/learner/dashboard"))["data"]
        o = dash["overview"]
        assert o["tracked"] == 3
        assert o["assessed"] + o["unassessed"] == o["tracked"]
        assert o["unassessed"] >= 1 and o["recommendations"] == len(recs)
        names = {x["node_id"]: x for x in dash["concepts"]}
        assert names[c["other"]["id"]]["state"] == "NOT_ASSESSED"
        assert names[c["other"]["id"]]["mastery"] is None
        assert o["weak"] == sum(1 for x in dash["concepts"] if x["state"] == "LEARNING")

        # complete one, dismiss another; neither returns during the cooldown
        first = recs[0]
        done = await post(client, alice, f"/recommendations/learner/{first['id']}/complete")
        assert done.status_code == 200 and done.json()["data"]["status"] == "completed"
        if len(recs) > 1:
            gone = await post(client, alice, f"/recommendations/learner/{recs[1]['id']}/dismiss")
            assert gone.json()["data"]["status"] == "dismissed"
            again = await post(client, alice, f"/recommendations/learner/{recs[1]['id']}/dismiss")
            assert again.status_code == 200 and again.json()["data"]["status"] == "dismissed"
        left = (await get(client, alice, "/recommendations/learner"))["data"]["items"]
        assert first["id"] not in {r["id"] for r in left}

    async def test_phase5_endpoints_are_unaffected(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        await wrong_quiz_with_concepts(client, study, alice, db_session)
        learner = (await get(client, alice, "/recommendations/learner"))["data"]["items"]
        old = (await get(client, alice, "/recommendations/revision"))["data"]["items"]
        assert {r["id"] for r in learner}.isdisjoint({r["id"] for r in old})
        assert all(
            r["recommendation_type"] in ("quiz", "flashcard", "topic", "chapter") for r in old
        )
        # a Phase 5 route cannot act on a learner row
        resp = await post(client, alice, f"/recommendations/{learner[0]['id']}/complete")
        assert resp.status_code == 404

    async def test_empty_account_dashboard_has_no_fake_data(
        self, client: AsyncClient, alice: Actor
    ) -> None:
        dash = (await get(client, alice, "/knowledge/learner/dashboard"))["data"]
        assert dash["overview"]["tracked"] == 0 and dash["concepts"] == []
        assert (await get(client, alice, "/recommendations/learner"))["data"]["items"] == []

    async def test_subject_filter_with_unknown_subject_is_empty(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        await wrong_quiz_with_concepts(client, study, alice, db_session)
        dash = (
            await get(
                client,
                alice,
                "/knowledge/learner/dashboard?subject_id=00000000-0000-0000-0000-000000000001",
            )
        )["data"]
        assert dash["overview"]["tracked"] == 0


class TestLearnerIsolation:
    async def test_other_user_sees_and_changes_nothing(
        self,
        client: AsyncClient,
        study: Harness,
        alice: Actor,
        bob: Actor,
        db_session: AsyncSession,
    ) -> None:
        c = await wrong_quiz_with_concepts(client, study, alice, db_session)
        rec = (await get(client, alice, "/recommendations/learner"))["data"]["items"][0]

        assert (await get(client, bob, "/knowledge/learner/dashboard"))["data"]["overview"][
            "tracked"
        ] == 0
        assert (await get(client, bob, "/knowledge/learner/evidence"))["total"] == 0
        assert (await get(client, bob, "/recommendations/learner"))["data"]["items"] == []
        assert (
            await _call(client, bob, "GET", f"/knowledge/learner/states/{c['krebs']['id']}")
        ).status_code == 404
        for action in ("complete", "dismiss"):
            resp = await post(client, bob, f"/recommendations/learner/{rec['id']}/{action}")
            assert resp.status_code == 404
        detect = await post(
            client,
            bob,
            "/knowledge/learner/misconceptions/detect",
            json={"node_id": c["krebs"]["id"]},
        )
        assert detect.status_code == 404
        # Alice's recommendation is still pending
        mine = (await get(client, alice, "/recommendations/learner"))["data"]["items"]
        assert rec["id"] in {r["id"] for r in mine}
