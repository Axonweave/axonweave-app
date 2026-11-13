"""Web-grounded subject graph (D-144): job creation, ownership, the run, evidence and clearing.

FakeProvider only: the scripted `sources` stand in for the provider's search grounding, so there is
no network and no cost."""

import json
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.types import WebSource
from app.knowledge.extraction import ExtractionDeps, run_extraction
from app.models.knowledge import KnowledgeEvidence, KnowledgeExtractionJob
from app.repositories.ai_usage_repository import AiUsageRepository
from tests.conftest import _TestSessionLocal
from tests.knowledge.test_clear_graph import clear
from tests.retrieval.test_search import Actor
from tests.study.conftest import Harness
from tests.test_closeout_users_config import _call

SITE_A = WebSource(
    url="https://example.org/cells",
    title="Cell biology primer",
    segments=("Mitochondria are organelles that make ATP by cellular respiration.",),
)
SITE_B = WebSource(
    url="https://example.net/atp",
    title="ATP explained",
    segments=("ATP is the energy currency of the cell and powers many reactions.",),
)


def concept(name: str, quote: str, source: int = 1, **kw: Any) -> dict[str, Any]:
    return {
        "name": name,
        "type": "concept",
        "description": f"About {name}.",
        "definition": None,
        "aliases": [],
        "difficulty": None,
        "confidence": 0.9,
        "evidence": [{"source": source, "quote": quote}],
        **kw,
    }


GOOD = json.dumps(
    {
        "concepts": [
            concept("Mitochondria", "organelles that make ATP"),
            concept("ATP", "energy currency of the cell", 2),
            # dropped: the quote is not in the passage it cites
            concept("Ribosome", "makes proteins in the cytoplasm"),
        ],
        "relationships": [
            {
                "source": "Mitochondria",
                "target": "ATP",
                "type": "RELATED_TO",
                "statement": "stated",
                "description": "Mitochondria make ATP.",
                "confidence": 0.8,
                "evidence": [{"source": 1, "quote": "make ATP by cellular respiration"}],
            }
        ],
    }
)


async def start_web(client: AsyncClient, who: Actor, subject_id: Any = None) -> Any:
    sid = subject_id or who.subject.id
    return await _call(client, who, "POST", "/knowledge/extract/web", json={"subject_id": str(sid)})


async def execute(lab: Harness, job_id: str) -> str:
    return await run_extraction(ExtractionDeps(_TestSessionLocal, lab.runtime), uuid.UUID(job_id))


async def job_row(job_id: str) -> KnowledgeExtractionJob:
    async with _TestSessionLocal() as db:
        row = (
            await db.execute(
                select(KnowledgeExtractionJob).where(KnowledgeExtractionJob.id == job_id)
            )
        ).scalar_one()
        return row


async def run_ok(client: AsyncClient, who: Actor, lab: Harness) -> str:
    lab.provider.sources = (SITE_A, SITE_B)
    lab.provider.reply = GOOD
    resp = await start_web(client, who)
    assert resp.status_code == 202, resp.text
    job_id = str(resp.json()["data"]["id"])
    assert await execute(lab, job_id) == "completed"
    return job_id


class TestCreate:
    async def test_queues_one_web_job_for_the_subject(
        self, client: AsyncClient, alice: Actor, lab: Harness
    ) -> None:
        resp = await start_web(client, alice)
        assert resp.status_code == 202, resp.text
        data = resp.json()["data"]
        assert data["source_kind"] == "web" and data["document_id"] is None
        assert data["subject_id"] == str(alice.subject.id) and data["topic"] == alice.subject.name
        assert len(lab.dispatcher.sent) == 1

    async def test_a_second_click_returns_the_running_job(
        self, client: AsyncClient, alice: Actor, lab: Harness
    ) -> None:
        first = (await start_web(client, alice)).json()["data"]
        again = await start_web(client, alice)
        assert again.status_code == 200
        assert again.json()["data"]["id"] == first["id"] and again.json()["data"]["existing"]
        assert len(lab.dispatcher.sent) == 1

    async def test_another_users_subject_is_404_and_queues_nothing(
        self, client: AsyncClient, alice: Actor, bob: Actor, lab: Harness
    ) -> None:
        resp = await start_web(client, bob, alice.subject.id)
        assert resp.status_code == 404
        assert lab.dispatcher.sent == []

    async def test_no_provider_and_no_broker_are_503(
        self, client: AsyncClient, alice: Actor, lab: Harness
    ) -> None:
        lab.dispatcher.is_available = False
        assert (await start_web(client, alice)).status_code == 503
        lab.dispatcher.is_available = True
        lab.unconfigured()
        assert (await start_web(client, alice)).status_code == 503
        assert lab.dispatcher.sent == []

    async def test_exhausted_daily_quota_is_429(
        self,
        client: AsyncClient,
        alice: Actor,
        lab: Harness,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        async def tokens_today(self: Any, user_id: Any) -> int:
            return 10**9

        monkeypatch.setattr(AiUsageRepository, "tokens_today", tokens_today)
        resp = await start_web(client, alice)
        assert resp.status_code == 429 and resp.json()["error"]["code"] == "AI_QUOTA_EXCEEDED"
        assert lab.dispatcher.sent == []

    async def test_requires_authentication(self, client: AsyncClient, alice: Actor) -> None:
        resp = await client.post(
            "/api/v1/knowledge/extract/web", json={"subject_id": str(alice.subject.id)}
        )
        assert resp.status_code in (401, 403)

    async def test_the_job_shows_in_the_subjects_run_list(
        self, client: AsyncClient, alice: Actor, bob: Actor, lab: Harness
    ) -> None:
        await start_web(client, alice)
        mine = await _call(
            client, alice, "GET", f"/knowledge/extract?subject_id={alice.subject.id}"
        )
        assert [j["source_kind"] for j in mine.json()["data"]] == ["web"]
        theirs = await _call(
            client, bob, "GET", f"/knowledge/extract?subject_id={alice.subject.id}"
        )
        assert theirs.json()["data"] == []


class TestRun:
    async def test_saves_verified_concepts_with_website_evidence(
        self, client: AsyncClient, alice: Actor, lab: Harness
    ) -> None:
        job_id = await run_ok(client, alice, lab)
        nodes = (await _call(client, alice, "GET", "/knowledge/nodes?limit=100")).json()["data"]
        by_name = {n["name"]: n for n in nodes}
        assert set(by_name) == {"Mitochondria", "ATP"}  # the unsupported "Ribosome" was dropped
        assert all(n["origin"] == "extracted" for n in nodes)
        assert all(n["subject_id"] == str(alice.subject.id) for n in nodes)

        evidence = (
            await _call(
                client, alice, "GET", f"/knowledge/nodes/{by_name['Mitochondria']['id']}/evidence"
            )
        ).json()["data"]
        assert len(evidence) == 1
        ev = evidence[0]
        assert ev["source_kind"] == "web" and ev["source_url"] == SITE_A.url
        assert ev["source_title"] == SITE_A.title
        assert ev["document_id"] is None and ev["document_name"] is None
        assert "organelles that make ATP" in ev["quote"]

        stats = (await job_row(job_id)).result_stats or {}
        assert stats["nodes_created"] == 2 and stats["edges_created"] == 1
        assert stats["evidence_added"] == 3

    async def test_a_second_run_adds_no_duplicates(
        self, client: AsyncClient, alice: Actor, lab: Harness
    ) -> None:
        job_id = await run_ok(client, alice, lab)
        async with _TestSessionLocal() as db:  # finished: a new run is allowed
            await db.execute(
                update(KnowledgeExtractionJob)
                .where(KnowledgeExtractionJob.id == job_id)
                .values(status="completed")
            )
            await db.commit()
        await run_ok(client, alice, lab)
        assert (await _call(client, alice, "GET", "/knowledge/nodes?limit=100")).json()[
            "total"
        ] == 2
        async with _TestSessionLocal() as db:
            rows = (await db.execute(select(KnowledgeEvidence))).scalars().all()
        assert len(rows) == 3

    async def test_no_sources_fails_clearly_and_saves_nothing(
        self, client: AsyncClient, alice: Actor, lab: Harness
    ) -> None:
        lab.provider.sources = ()
        lab.provider.reply = GOOD
        job_id = str((await start_web(client, alice)).json()["data"]["id"])
        assert await execute(lab, job_id) == "failed"
        row = await job_row(job_id)
        assert row.error_code == "KNOWLEDGE_NO_WEB_SOURCES"
        assert (await _call(client, alice, "GET", "/knowledge/nodes")).json()["total"] == 0
        shown = (await _call(client, alice, "GET", f"/knowledge/extract/{job_id}")).json()["data"]
        assert "no usable sources" in shown["error_message"]

    async def test_unsafe_or_unusable_sources_are_ignored(
        self, client: AsyncClient, alice: Actor, lab: Harness
    ) -> None:
        lab.provider.sources = (
            WebSource(url="http://example.org/plain", title="http", segments=("organelles",)),
            WebSource(url="javascript:alert(1)", title="js", segments=("organelles",)),
            WebSource(url="https://user:pw@example.org/x", title="creds", segments=("organelles",)),
            WebSource(url="https://example.org/empty", title="empty", segments=("  ",)),
        )
        lab.provider.reply = GOOD
        job_id = str((await start_web(client, alice)).json()["data"]["id"])
        assert await execute(lab, job_id) == "failed"
        assert (await job_row(job_id)).error_code == "KNOWLEDGE_NO_WEB_SOURCES"

    async def test_only_https_links_are_stored(
        self, client: AsyncClient, alice: Actor, lab: Harness
    ) -> None:
        await run_ok(client, alice, lab)
        async with _TestSessionLocal() as db:
            urls = (await db.execute(select(KnowledgeEvidence.source_url))).scalars().all()
        assert urls and all(u and u.startswith("https://") for u in urls)

    async def test_invalid_model_output_fails_without_saving(
        self, client: AsyncClient, alice: Actor, lab: Harness
    ) -> None:
        lab.provider.sources = (SITE_A,)
        lab.provider.reply = "not json"
        job_id = str((await start_web(client, alice)).json()["data"]["id"])
        assert await execute(lab, job_id) == "failed"
        assert (await _call(client, alice, "GET", "/knowledge/nodes")).json()["total"] == 0

    async def test_every_provider_call_is_counted_as_extraction_usage(
        self, client: AsyncClient, alice: Actor, lab: Harness
    ) -> None:
        job_id = await run_ok(client, alice, lab)
        assert (await job_row(job_id)).provider_calls == 2  # the search, then the extraction


class TestEvidenceAndClear:
    async def test_foreign_user_cannot_read_web_evidence(
        self, client: AsyncClient, alice: Actor, bob: Actor, lab: Harness
    ) -> None:
        await run_ok(client, alice, lab)
        nodes = (await _call(client, alice, "GET", "/knowledge/nodes?limit=100")).json()["data"]
        resp = await _call(client, bob, "GET", f"/knowledge/nodes/{nodes[0]['id']}/evidence")
        assert resp.status_code == 404

    async def test_clearing_removes_finished_web_jobs_so_it_can_be_rebuilt(
        self, client: AsyncClient, alice: Actor, lab: Harness
    ) -> None:
        await run_ok(client, alice, lab)
        resp = await clear(client, alice, alice.subject.id)
        assert resp.status_code == 200 and resp.json()["data"]["concepts"] == 2
        listed = await _call(
            client, alice, "GET", f"/knowledge/extract?subject_id={alice.subject.id}"
        )
        assert listed.json()["data"] == []
        async with _TestSessionLocal() as db:
            assert (await db.execute(select(KnowledgeEvidence))).scalars().all() == []

    async def test_clearing_is_refused_while_a_web_run_is_active(
        self, client: AsyncClient, alice: Actor, lab: Harness
    ) -> None:
        await start_web(client, alice)
        resp = await clear(client, alice, alice.subject.id)
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "KNOWLEDGE_EXTRACTION_RUNNING"

    async def test_a_cancelled_web_run_saves_nothing(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, lab: Harness
    ) -> None:
        lab.provider.sources = (SITE_A, SITE_B)
        lab.provider.reply = GOOD
        job_id = str((await start_web(client, alice)).json()["data"]["id"])
        cancel = await _call(client, alice, "POST", f"/knowledge/extract/{job_id}/cancel")
        assert cancel.status_code == 200
        assert await execute(lab, job_id) in ("cancelled", "skipped")
        assert (await _call(client, alice, "GET", "/knowledge/nodes")).json()["total"] == 0
