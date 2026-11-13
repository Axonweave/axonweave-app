"""Clearing the knowledge graph of one subject: scope, confirmation, busy guard, regeneration."""

from typing import Any

from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import get_rate_limiter
from app.models.knowledge import KnowledgeExtractionJob
from tests.conftest import _TestSessionLocal
from tests.knowledge.test_extract_subject import lab, run_subject  # noqa: F401  (fixture)
from tests.knowledge.test_graph_api import edge, node
from tests.retrieval.test_search import Actor, add_doc
from tests.study.conftest import PHOTO, Harness
from tests.test_closeout_users_config import _call


async def clear(client: AsyncClient, who: Actor, subject_id: Any, confirm: Any = True) -> Any:
    return await _call(
        client,
        who,
        "POST",
        "/knowledge/graph/clear",
        json={"subject_id": str(subject_id), "confirm": confirm},
    )


async def total_nodes(client: AsyncClient, who: Actor) -> int:
    resp = await _call(client, who, "GET", "/knowledge/nodes?limit=100")
    return int(resp.json()["total"])


class TestClearGraph:
    async def test_removes_the_subjects_concepts_and_relationships_only(
        self, client: AsyncClient, alice: Actor
    ) -> None:
        sid = str(alice.subject.id)
        a = await node(client, alice, "Mitochondria", subject_id=sid)
        b = await node(client, alice, "ATP", subject_id=sid)
        await node(client, alice, "No subject concept")
        assert (await edge(client, alice, a["id"], b["id"])).status_code == 201

        resp = await clear(client, alice, alice.subject.id)
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"] == {"concepts": 2, "relationships": 1}
        assert await total_nodes(client, alice) == 1  # the concept without a subject stays

    async def test_confirmation_is_required(self, client: AsyncClient, alice: Actor) -> None:
        await node(client, alice, "Keep me", subject_id=str(alice.subject.id))
        assert (await clear(client, alice, alice.subject.id, confirm=False)).status_code == 422
        resp = await _call(
            client,
            alice,
            "POST",
            "/knowledge/graph/clear",
            json={"subject_id": str(alice.subject.id)},
        )
        assert resp.status_code == 422
        assert await total_nodes(client, alice) == 1

    async def test_another_users_subject_is_404_and_nothing_is_deleted(
        self, client: AsyncClient, alice: Actor, bob: Actor
    ) -> None:
        await node(client, alice, "Mine", subject_id=str(alice.subject.id))
        assert (await clear(client, bob, alice.subject.id)).status_code == 404
        assert await total_nodes(client, alice) == 1

    async def test_requires_authentication(self, client: AsyncClient, alice: Actor) -> None:
        resp = await client.post(
            "/api/v1/knowledge/graph/clear",
            json={"subject_id": str(alice.subject.id), "confirm": True},
        )
        assert resp.status_code in (401, 403)

    async def test_refused_while_an_extraction_is_running(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        alice: Actor,
        lab: Harness,  # noqa: F811
    ) -> None:
        await add_doc(db_session, alice, "A", [PHOTO])
        await node(client, alice, "Keep me", subject_id=str(alice.subject.id))
        assert (await run_subject(client, alice)).json()["data"]["queued"] == 1  # job is pending
        resp = await clear(client, alice, alice.subject.id)
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "KNOWLEDGE_EXTRACTION_RUNNING"
        assert await total_nodes(client, alice) == 1

    async def test_a_cleared_subject_can_be_generated_again(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        alice: Actor,
        lab: Harness,  # noqa: F811
    ) -> None:
        await add_doc(db_session, alice, "A", [PHOTO])
        first = (await run_subject(client, alice)).json()["data"]
        async with _TestSessionLocal() as db:  # the run finished
            await db.execute(
                update(KnowledgeExtractionJob)
                .where(KnowledgeExtractionJob.id == first["job_ids"][0])
                .values(status="completed")
            )
            await db.commit()
        get_rate_limiter().reset()
        assert (await run_subject(client, alice)).json()["data"]["skipped"] == 1

        assert (await clear(client, alice, alice.subject.id)).status_code == 200
        get_rate_limiter().reset()
        again = (await run_subject(client, alice)).json()["data"]
        assert (again["skipped"], again["queued"]) == (0, 1)
