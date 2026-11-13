"""Whole-subject extraction: one job per ready document, owner scoping, skip, cap and limits.

FakeProvider only: no network, no cost. Only job creation is tested here; the run itself is the
per-document worker and is unchanged."""

from collections.abc import Generator
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.dispatch import get_extraction_dispatcher
from app.main import app
from app.models.knowledge import KnowledgeExtractionJob
from app.repositories.ai_usage_repository import AiUsageRepository
from tests.conftest import _TestSessionLocal
from tests.retrieval.test_search import Actor, add_doc
from tests.study.conftest import KREBS, PHOTO, Harness
from tests.test_closeout_users_config import _call


@pytest.fixture
def lab(study: Harness) -> Generator[Harness]:
    app.dependency_overrides[get_extraction_dispatcher] = lambda: study.dispatcher
    yield study
    app.dependency_overrides.pop(get_extraction_dispatcher, None)


async def run_subject(client: AsyncClient, who: Actor, subject_id: Any = None) -> Any:
    sid = subject_id or who.subject.id
    return await _call(
        client, who, "POST", "/knowledge/extract/subject", json={"subject_id": str(sid)}
    )


class TestSubjectExtraction:
    async def test_queues_one_job_per_ready_document(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, lab: Harness
    ) -> None:
        first = await add_doc(db_session, alice, "A", [PHOTO])
        second = await add_doc(db_session, alice, "B", [KREBS])
        resp = await run_subject(client, alice)
        assert resp.status_code == 202, resp.text
        data = resp.json()["data"]
        assert (data["ready"], data["queued"], data["skipped"]) == (2, 2, 0)
        assert len(data["job_ids"]) == 2 and len(lab.dispatcher.sent) == 2
        jobs = await _call(
            client, alice, "GET", f"/knowledge/extract?subject_id={alice.subject.id}"
        )
        assert {j["document_id"] for j in jobs.json()["data"]} == {str(first.id), str(second.id)}

    async def test_unprocessed_and_archived_documents_are_ignored(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, lab: Harness
    ) -> None:
        await add_doc(db_session, alice, "ok", [PHOTO])
        await add_doc(db_session, alice, "busy", [KREBS], status="extracting")
        await add_doc(db_session, alice, "old", [KREBS], archived=True)
        data = (await run_subject(client, alice)).json()["data"]
        assert (data["ready"], data["queued"]) == (1, 1)

    async def test_already_extracted_documents_are_skipped(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, lab: Harness
    ) -> None:
        await add_doc(db_session, alice, "A", [PHOTO])
        await add_doc(db_session, alice, "B", [KREBS])
        first = (await run_subject(client, alice)).json()["data"]
        async with _TestSessionLocal() as db:  # pretend the first job finished
            await db.execute(
                update(KnowledgeExtractionJob)
                .where(KnowledgeExtractionJob.id == first["job_ids"][0])
                .values(status="completed")
            )
            await db.commit()
        lab.configure()  # a new run, with the per-subject minute limit reset
        from app.core.rate_limit import get_rate_limiter

        get_rate_limiter().reset()
        data = (await run_subject(client, alice)).json()["data"]
        assert data["skipped"] == 1 and data["queued"] == 0 and data["already_running"] == 1

    async def test_batch_is_capped(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, lab: Harness
    ) -> None:
        lab.configure(knowledge_max_documents_per_subject_run=2)
        for n in range(3):
            await add_doc(db_session, alice, f"D{n}", [PHOTO])
        data = (await run_subject(client, alice)).json()["data"]
        assert (data["queued"], data["over_cap"]) == (2, 1)

    async def test_clicking_again_returns_the_running_jobs_without_waiting(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, lab: Harness
    ) -> None:
        await add_doc(db_session, alice, "A", [PHOTO])
        first = (await run_subject(client, alice)).json()["data"]
        again = await run_subject(client, alice)  # no cooldown
        assert again.status_code == 202
        data = again.json()["data"]
        assert (data["queued"], data["already_running"]) == (0, 1)
        assert data["job_ids"] == first["job_ids"] and len(lab.dispatcher.sent) == 1

    async def test_an_exhausted_daily_quota_is_reported_and_does_not_block_the_next_try(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        alice: Actor,
        lab: Harness,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        await add_doc(db_session, alice, "A", [PHOTO])
        used = {"tokens": 10**9}

        async def tokens_today(self: Any, user_id: Any) -> int:
            return int(used["tokens"])

        monkeypatch.setattr(AiUsageRepository, "tokens_today", tokens_today)
        resp = await run_subject(client, alice)
        assert resp.status_code == 429
        assert resp.json()["error"]["code"] == "AI_QUOTA_EXCEEDED"
        assert lab.dispatcher.sent == []
        used["tokens"] = 0  # quota available again: the very next click works, nothing to wait for
        assert (await run_subject(client, alice)).status_code == 202

    async def test_empty_subject_queues_nothing(
        self, client: AsyncClient, alice: Actor, lab: Harness
    ) -> None:
        data = (await run_subject(client, alice)).json()["data"]
        assert data["ready"] == 0 and data["queued"] == 0 and lab.dispatcher.sent == []

    async def test_no_provider_and_no_broker_are_503(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, lab: Harness
    ) -> None:
        await add_doc(db_session, alice, "A", [PHOTO])
        lab.dispatcher.is_available = False
        assert (await run_subject(client, alice)).status_code == 503
        lab.dispatcher.is_available = True
        lab.unconfigured()
        assert (await run_subject(client, alice)).status_code == 503
        assert lab.dispatcher.sent == []

    async def test_another_users_subject_is_404_and_queues_nothing(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        alice: Actor,
        bob: Actor,
        lab: Harness,
    ) -> None:
        await add_doc(db_session, alice, "A", [PHOTO])
        resp = await run_subject(client, bob, alice.subject.id)
        assert resp.status_code == 404
        assert lab.dispatcher.sent == []
        listed = await _call(
            client, bob, "GET", f"/knowledge/extract?subject_id={alice.subject.id}"
        )
        assert listed.json()["data"] == []

    async def test_requires_authentication(self, client: AsyncClient, alice: Actor) -> None:
        resp = await client.post(
            "/api/v1/knowledge/extract/subject", json={"subject_id": str(alice.subject.id)}
        )
        assert resp.status_code in (401, 403)
