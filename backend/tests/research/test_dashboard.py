"""Phase 7 M7.11: dashboard counts come from the owner's own rows only."""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.research.test_comparisons import DATASET_A, RESULT_A, analysed_paper
from tests.research.test_projects_api import make as make_project
from tests.retrieval.test_search import Actor
from tests.study.conftest import Harness
from tests.test_closeout_users_config import _call


async def dash(client: AsyncClient, who: Actor, path: str = "/research/dashboard") -> dict:
    resp = await _call(client, who, "GET", path)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


class TestDashboard:
    async def test_empty_account_has_zeros_and_no_activity(
        self, client: AsyncClient, alice: Actor
    ) -> None:
        data = await dash(client, alice)
        assert data["recent"] == []
        assert all(v == 0 for v in data["counts"].values())

    async def test_counts_reflect_real_rows(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, lab: Harness
    ) -> None:
        project = await make_project(client, alice)
        await analysed_paper(
            client,
            db_session,
            alice,
            lab,
            project["id"],
            "Paper A",
            results=[RESULT_A],
            dataset=[DATASET_A],
        )
        draft = await _call(
            client,
            alice,
            "POST",
            f"/research/projects/{project['id']}/drafts",
            json={"title": "My draft", "document_type": "notes"},
        )
        assert draft.status_code == 201, draft.text
        overall = await dash(client, alice)
        counts = overall["counts"]
        assert counts["active_projects"] == 1
        assert counts["papers"] == 1 and counts["papers_analysed"] == 1
        assert counts["papers_awaiting"] == 0 and counts["drafts_in_progress"] == 1
        kinds = {r["kind"] for r in overall["recent"]}
        assert {"paper_added", "draft_updated"} <= kinds
        scoped = await dash(client, alice, f"/research/projects/{project['id']}/dashboard")
        assert scoped["counts"]["papers"] == 1 and scoped["counts"]["active_projects"] is None

    async def test_archived_projects_are_left_out_of_the_overview(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, lab: Harness
    ) -> None:
        project = await make_project(client, alice)
        await analysed_paper(
            client,
            db_session,
            alice,
            lab,
            project["id"],
            "Paper A",
            results=[RESULT_A],
            dataset=[DATASET_A],
        )
        await _call(client, alice, "POST", f"/research/projects/{project['id']}/archive")
        counts = (await dash(client, alice))["counts"]
        assert counts["active_projects"] == 0 and counts["papers"] == 0

    async def test_other_users_see_nothing_and_get_404_for_a_project(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, bob: Actor, lab: Harness
    ) -> None:
        project = await make_project(client, alice)
        await analysed_paper(
            client,
            db_session,
            alice,
            lab,
            project["id"],
            "Paper A",
            results=[RESULT_A],
            dataset=[DATASET_A],
        )
        theirs = await dash(client, bob)
        assert theirs["recent"] == [] and theirs["counts"]["papers"] == 0
        resp = await _call(client, bob, "GET", f"/research/projects/{project['id']}/dashboard")
        assert resp.status_code == 404
