"""Phase 7 M7.3: structured paper analysis (run, verification, evidence, versions, notes, access).

FakeProvider only: no network, no cost. The fake model replies with scripted JSON."""

import json
import uuid
from collections.abc import Generator
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import get_rate_limiter
from app.knowledge.extraction import ExtractionDeps
from app.main import app
from app.models.ai_usage_record import AiUsageRecord
from app.research.analysis import (
    AnalysisOutput,
    parse_analysis,
    verify_analysis,
)
from app.research.analysis_dispatch import get_analysis_dispatcher
from app.research.analysis_run import run_paper_analysis
from app.study.generators.base import OutputInvalid
from app.study.source_reader import SourceUnit
from tests.conftest import _TestSessionLocal
from tests.research.test_projects_api import make as make_project
from tests.retrieval.test_search import Actor, add_doc
from tests.study.conftest import KREBS, PHOTO, Harness, two_docs
from tests.test_closeout_users_config import _call


def claim(text: str, quote: str, source: int = 1, **kw: Any) -> dict[str, Any]:
    return {
        "label": None,
        "text": text,
        "origin": "reported",
        "confidence": 0.9,
        "evidence": [{"source": source, "quote": quote}],
        **kw,
    }


def reply(**sections: list[dict[str, Any]]) -> str:
    return json.dumps({name: {"items": items} for name, items in sections.items()})


GOOD = reply(
    results=[claim("Chloroplasts turn light into chemical energy.", "light energy into chemical")],
    dataset=[claim("The Krebs cycle runs in mitochondria.", "acetyl-CoA to carbon dioxide", 2)],
    limitations=[
        claim(
            "Only plant and mitochondrial processes are covered.",
            "inside chloroplasts",
            origin="ai_inferred",
        )
    ],
    # dropped: the quotation is not in the passage
    methodology=[claim("A randomised trial of 400 subjects.", "randomised trial of 400 subjects")],
    # dropped: inference is only allowed for limitations
    objectives=[claim("It probably aims to cure cancer.", "Krebs cycle", 2, origin="ai_inferred")],
)


@pytest.fixture
def lab(study: Harness) -> Generator[Harness]:
    app.dependency_overrides[get_analysis_dispatcher] = lambda: study.dispatcher
    study.provider.reply = GOOD
    yield study
    app.dependency_overrides.pop(get_analysis_dispatcher, None)


async def paper_with_file(
    client: AsyncClient, db: AsyncSession, who: Actor, **kw: Any
) -> tuple[dict[str, Any], dict[str, Any]]:
    project = await make_project(client, who)
    doc = await two_docs(db, who)
    resp = await _call(
        client,
        who,
        "POST",
        f"/research/projects/{project['id']}/papers",
        json={"title": "Cell energy paper", "document_id": str(doc.id), **kw},
    )
    assert resp.status_code == 201, resp.text
    return project, resp.json()["data"]


async def start(client: AsyncClient, who: Actor, paper_id: str) -> Any:
    return await _call(client, who, "POST", f"/research/papers/{paper_id}/analyses")


async def execute(lab: Harness, run_id: str) -> str:
    return await run_paper_analysis(
        ExtractionDeps(_TestSessionLocal, lab.runtime), uuid.UUID(run_id)
    )


async def analysis(client: AsyncClient, who: Actor, paper_id: str, qs: str = "") -> dict[str, Any]:
    resp = await _call(client, who, "GET", f"/research/papers/{paper_id}/analysis{qs}")
    assert resp.status_code == 200, resp.text
    data: dict[str, Any] = resp.json()["data"]
    return data


async def paper_status(client: AsyncClient, who: Actor, paper_id: str) -> str:
    resp = await _call(client, who, "GET", f"/research/papers/{paper_id}")
    return str(resp.json()["data"]["analysis_status"])


def section(data: dict[str, Any], name: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = next(s for s in data["sections"] if s["section"] == name)["items"]
    return items


class TestVerification:
    def units(self) -> list[SourceUnit]:
        return [
            SourceUnit(uuid.uuid4(), uuid.uuid4(), "p.pdf", 0, PHOTO, 3, None, None, 10),
            SourceUnit(uuid.uuid4(), uuid.uuid4(), "p.pdf", 1, KREBS, 4, None, None, 10),
        ]

    def test_only_quoted_claims_survive_and_inference_is_limited(self) -> None:
        out = verify_analysis(parse_analysis(GOOD), self.units())
        assert [len(out.sections[n]) for n in ("results", "dataset", "limitations")] == [1, 1, 1]
        assert out.sections["methodology"] == [] and out.sections["objectives"] == []
        assert out.dropped == 2 and out.claim_count == 3

    def test_quote_must_come_from_the_cited_passage(self) -> None:
        wrong = reply(results=[claim("x claim", "acetyl-CoA to carbon dioxide", source=1)])
        assert verify_analysis(parse_analysis(wrong), self.units()).claim_count == 0

    def test_unknown_source_number_is_never_trusted(self) -> None:
        ghost = reply(results=[claim("ghost claim", "light energy", source=99)])
        assert verify_analysis(parse_analysis(ghost), self.units()).claim_count == 0

    def test_repeated_claims_are_collapsed(self) -> None:
        twice = reply(results=[claim("Same finding.", "light energy")] * 2)
        out = verify_analysis(parse_analysis(twice), self.units())
        assert len(out.sections["results"]) == 1 and out.dropped == 1

    def test_malformed_output_is_rejected(self) -> None:
        for raw in ("not json", json.dumps({"results": {"items": [{"text": "no evidence"}]}})):
            with pytest.raises(OutputInvalid):
                parse_analysis(raw)
        assert AnalysisOutput.model_validate({}).results.items == []


class TestRun:
    async def test_full_run_stores_verified_claims_and_evidence(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, lab: Harness
    ) -> None:
        _, paper = await paper_with_file(client, db_session, alice)
        resp = await start(client, alice, paper["id"])
        assert resp.status_code == 202, resp.text
        run = resp.json()["data"]
        assert run["status"] == "pending" and run["version_number"] == 1
        assert lab.dispatcher.sent == [uuid.UUID(run["id"])]
        assert await paper_status(client, alice, paper["id"]) == "queued"

        assert await execute(lab, run["id"]) == "completed"
        assert await paper_status(client, alice, paper["id"]) == "analysed"
        data = await analysis(client, alice, paper["id"])
        assert data["run"]["status"] == "completed" and data["active"] is None
        assert [s["section"] for s in data["sections"]][:3] == [
            "research_problem",
            "objectives",
            "methodology",
        ]
        results = section(data, "results")
        assert len(results) == 1 and results[0]["origin"] == "reported"
        assert results[0]["evidence"][0]["quote"] == "light energy into chemical"
        assert results[0]["evidence"][0]["document_id"] is not None
        assert results[0]["evidence"][0]["chunk_id"] is not None
        assert section(data, "limitations")[0]["origin"] == "ai_inferred"
        # nothing invented: uncovered and unverifiable sections stay empty
        for name in ("research_problem", "objectives", "methodology", "future_work"):
            assert section(data, name) == []
        assert data["run"]["result_stats"]["dropped"] == 2

        rows = (
            await db_session.execute(
                select(AiUsageRecord).where(AiUsageRecord.request_kind == "paper_analysis")
            )
        ).scalars()
        assert [r.request_status for r in rows] == ["success"]

    async def test_nothing_verifiable_fails_without_storing_results(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, lab: Harness
    ) -> None:
        lab.provider.reply = reply(results=[claim("Invented.", "words that are not there")])
        _, paper = await paper_with_file(client, db_session, alice)
        run = (await start(client, alice, paper["id"])).json()["data"]
        assert await execute(lab, run["id"]) == "failed"
        detail = (
            await _call(
                client, alice, "GET", f"/research/papers/{paper['id']}/analyses/{run['id']}"
            )
        ).json()["data"]
        assert detail["error_code"] == "RESEARCH_NOTHING_VERIFIED"
        assert "confirmed" in detail["error_message"]
        assert (await analysis(client, alice, paper["id"]))["run"] is None
        assert await paper_status(client, alice, paper["id"]) == "failed"

    async def test_one_correction_call_for_malformed_output(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, lab: Harness
    ) -> None:
        lab.provider.replies = ["this is not json", GOOD]
        _, paper = await paper_with_file(client, db_session, alice)
        run = (await start(client, alice, paper["id"])).json()["data"]
        assert await execute(lab, run["id"]) == "completed"
        rows = list(
            (
                await db_session.execute(
                    select(AiUsageRecord).where(AiUsageRecord.request_kind == "paper_analysis")
                )
            ).scalars()
        )
        assert len(rows) == 2

    async def test_two_malformed_replies_fail_the_run(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, lab: Harness
    ) -> None:
        lab.provider.replies = ["nope", "still nope"]
        _, paper = await paper_with_file(client, db_session, alice)
        run = (await start(client, alice, paper["id"])).json()["data"]
        assert await execute(lab, run["id"]) == "failed"
        detail = (
            await _call(
                client, alice, "GET", f"/research/papers/{paper['id']}/analyses/{run['id']}"
            )
        ).json()["data"]
        assert detail["error_code"] == "RESEARCH_INVALID_OUTPUT"

    async def test_reanalysis_is_a_new_version_and_keeps_the_old_one_and_notes(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, lab: Harness
    ) -> None:
        _, paper = await paper_with_file(client, db_session, alice)
        first = (await start(client, alice, paper["id"])).json()["data"]
        assert await execute(lab, first["id"]) == "completed"
        note = await _call(
            client,
            alice,
            "POST",
            f"/research/papers/{paper['id']}/notes",
            json={"section": "results", "body": "Check the sample size."},
        )
        assert note.status_code == 201

        lab.provider.reply = reply(
            results=[claim("A different reading.", "Krebs cycle oxidises", 2)]
        )
        second = (await start(client, alice, paper["id"])).json()["data"]
        assert second["version_number"] == 2 and second["id"] != first["id"]
        assert await execute(lab, second["id"]) == "completed"

        latest = await analysis(client, alice, paper["id"])
        assert latest["run"]["version_number"] == 2
        assert section(latest, "results")[0]["text"] == "A different reading."
        old = await analysis(client, alice, paper["id"], "?version=1")
        assert section(old, "results")[0]["text"].startswith("Chloroplasts")
        history = (
            await _call(client, alice, "GET", f"/research/papers/{paper['id']}/analyses")
        ).json()
        assert [r["version_number"] for r in history["data"]] == [2, 1]

        notes = (await _call(client, alice, "GET", f"/research/papers/{paper['id']}/notes")).json()
        assert [n["body"] for n in notes["data"]] == ["Check the sample size."]
        missing = await _call(
            client, alice, "GET", f"/research/papers/{paper['id']}/analysis?version=9"
        )
        assert missing.status_code == 404

    async def test_a_failed_rerun_does_not_hide_the_earlier_result(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, lab: Harness
    ) -> None:
        _, paper = await paper_with_file(client, db_session, alice)
        first = (await start(client, alice, paper["id"])).json()["data"]
        await execute(lab, first["id"])
        lab.provider.reply = "garbage"
        second = (await start(client, alice, paper["id"])).json()["data"]
        assert await execute(lab, second["id"]) == "failed"
        assert await paper_status(client, alice, paper["id"]) == "analysed"
        assert (await analysis(client, alice, paper["id"]))["run"]["version_number"] == 1

    async def test_a_second_start_while_active_returns_the_active_run(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, lab: Harness
    ) -> None:
        _, paper = await paper_with_file(client, db_session, alice)
        one = await start(client, alice, paper["id"])
        two = await start(client, alice, paper["id"])
        assert one.status_code == 202 and two.status_code == 200
        assert two.json()["data"]["id"] == one.json()["data"]["id"]
        assert two.json()["data"]["existing"] is True
        assert len(lab.dispatcher.sent) == 1
        active = (await analysis(client, alice, paper["id"]))["active"]
        assert active["id"] == one.json()["data"]["id"]

    async def test_cancelling_a_pending_run_stops_it(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, lab: Harness
    ) -> None:
        _, paper = await paper_with_file(client, db_session, alice)
        run = (await start(client, alice, paper["id"])).json()["data"]
        cancelled = await _call(
            client, alice, "POST", f"/research/papers/{paper['id']}/analyses/{run['id']}/cancel"
        )
        assert cancelled.json()["data"]["status"] == "cancelled"
        assert await paper_status(client, alice, paper["id"]) == "not_analysed"
        assert await execute(lab, run["id"]) == "skipped"
        again = await _call(
            client, alice, "POST", f"/research/papers/{paper['id']}/analyses/{run['id']}/cancel"
        )
        assert (
            again.status_code == 409 and again.json()["error"]["code"] == "RESEARCH_NOT_CANCELLABLE"
        )


class TestStartRules:
    async def test_a_paper_without_a_file_cannot_be_analysed(
        self, client: AsyncClient, alice: Actor, lab: Harness
    ) -> None:
        project = await make_project(client, alice)
        made = await _call(
            client,
            alice,
            "POST",
            f"/research/projects/{project['id']}/papers",
            json={"title": "Metadata only"},
        )
        resp = await start(client, alice, made.json()["data"]["id"])
        assert (
            resp.status_code == 422 and resp.json()["error"]["code"] == "RESEARCH_PAPER_HAS_NO_FILE"
        )

    async def test_a_file_still_processing_is_not_ready(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, lab: Harness
    ) -> None:
        project = await make_project(client, alice)
        doc = await add_doc(db_session, alice, "Pending", [PHOTO], status="queued")
        made = await _call(
            client,
            alice,
            "POST",
            f"/research/projects/{project['id']}/papers",
            json={"title": "Queued file", "document_id": str(doc.id)},
        )
        resp = await start(client, alice, made.json()["data"]["id"])
        assert (
            resp.status_code == 422
            and resp.json()["error"]["code"] == "RESEARCH_DOCUMENT_NOT_READY"
        )

    async def test_archived_paper_is_refused(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, lab: Harness
    ) -> None:
        _, paper = await paper_with_file(client, db_session, alice)
        await _call(client, alice, "POST", f"/research/papers/{paper['id']}/archive")
        resp = await start(client, alice, paper["id"])
        assert resp.status_code == 409 and resp.json()["error"]["code"] == "RESEARCH_PAPER_ARCHIVED"

    async def test_no_provider_is_503_and_no_broker_is_503(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, lab: Harness
    ) -> None:
        _, paper = await paper_with_file(client, db_session, alice)
        lab.dispatcher.is_available = False
        resp = await start(client, alice, paper["id"])
        assert (
            resp.status_code == 503
            and resp.json()["error"]["code"] == "RESEARCH_ANALYSIS_UNAVAILABLE"
        )
        lab.dispatcher.is_available = True
        lab.unconfigured()
        resp = await start(client, alice, paper["id"])
        assert resp.status_code == 503 and resp.json()["error"]["code"] == "LLM_NOT_CONFIGURED"

    async def test_per_minute_limit_and_daily_quota(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, lab: Harness
    ) -> None:
        _, paper = await paper_with_file(client, db_session, alice)
        lab.configure(research_analysis_requests_per_minute_per_user=1)
        get_rate_limiter().reset()
        first = (await start(client, alice, paper["id"])).json()["data"]
        await execute(lab, first["id"])
        limited = await start(client, alice, paper["id"])
        assert (
            limited.status_code == 429
            and limited.json()["error"]["code"] == "RESEARCH_RATE_LIMITED"
        )

        lab.configure(ai_daily_token_quota=1)
        get_rate_limiter().reset()
        quota = await start(client, alice, paper["id"])
        assert quota.status_code == 429, quota.text

    async def test_active_cap(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, lab: Harness
    ) -> None:
        lab.configure(research_max_active_analyses_per_user=1)
        _, one = await paper_with_file(client, db_session, alice)
        _, two = await paper_with_file(client, db_session, alice)
        assert (await start(client, alice, one["id"])).status_code == 202
        capped = await start(client, alice, two["id"])
        assert (
            capped.status_code == 429
            and capped.json()["error"]["code"] == "RESEARCH_TOO_MANY_ACTIVE"
        )


class TestNotes:
    async def test_note_crud(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, lab: Harness
    ) -> None:
        _, paper = await paper_with_file(client, db_session, alice)
        base = f"/research/papers/{paper['id']}/notes"
        made = await _call(client, alice, "POST", base, json={"body": "  General note  "})
        assert made.status_code == 201 and made.json()["data"]["body"] == "General note"
        note_id = made.json()["data"]["id"]
        bad = await _call(client, alice, "POST", base, json={"section": "nonsense", "body": "x"})
        assert bad.status_code == 422
        empty = await _call(client, alice, "POST", base, json={"body": "   "})
        assert empty.status_code == 422
        edited = await _call(
            client, alice, "PATCH", f"/research/notes/{note_id}", json={"body": "Edited"}
        )
        assert edited.json()["data"]["body"] == "Edited"
        assert (
            await _call(client, alice, "DELETE", f"/research/notes/{note_id}")
        ).status_code == 204
        listing = (await _call(client, alice, "GET", base)).json()
        assert listing["data"] == []


class TestOwnership:
    async def test_other_users_get_404_everywhere(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        alice: Actor,
        bob: Actor,
        lab: Harness,
    ) -> None:
        _, paper = await paper_with_file(client, db_session, alice)
        run = (await start(client, alice, paper["id"])).json()["data"]
        await execute(lab, run["id"])
        note = (
            await _call(
                client,
                alice,
                "POST",
                f"/research/papers/{paper['id']}/notes",
                json={"body": "mine"},
            )
        ).json()["data"]
        pid = paper["id"]
        calls: list[tuple[str, str, dict[str, Any] | None]] = [
            ("POST", f"/research/papers/{pid}/analyses", None),
            ("GET", f"/research/papers/{pid}/analyses", None),
            ("GET", f"/research/papers/{pid}/analysis", None),
            ("GET", f"/research/papers/{pid}/analyses/{run['id']}", None),
            ("POST", f"/research/papers/{pid}/analyses/{run['id']}/cancel", None),
            ("GET", f"/research/papers/{pid}/notes", None),
            ("POST", f"/research/papers/{pid}/notes", {"body": "intrusion"}),
            ("PATCH", f"/research/notes/{note['id']}", {"body": "hijack"}),
            ("DELETE", f"/research/notes/{note['id']}", None),
        ]
        for method, path, body in calls:
            resp = await _call(client, bob, method, path, json=body)
            assert resp.status_code == 404, (method, path, resp.status_code)
            assert resp.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
        # alice's data is untouched
        notes = (await _call(client, alice, "GET", f"/research/papers/{pid}/notes")).json()["data"]
        assert [n["body"] for n in notes] == ["mine"]

    async def test_an_analysis_id_from_another_paper_is_not_found(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, lab: Harness
    ) -> None:
        _, one = await paper_with_file(client, db_session, alice)
        _, two = await paper_with_file(client, db_session, alice)
        run = (await start(client, alice, one["id"])).json()["data"]
        resp = await _call(
            client, alice, "GET", f"/research/papers/{two['id']}/analyses/{run['id']}"
        )
        assert resp.status_code == 404

    async def test_requires_authentication(self, client: AsyncClient) -> None:
        resp = await client.get(f"/api/v1/research/papers/{uuid.uuid4()}/analysis")
        assert resp.status_code == 401
