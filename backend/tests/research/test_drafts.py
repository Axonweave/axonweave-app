"""Phase 7 M7.9: drafts, versions, evidence check, export and grounded writing assistance."""

import json
import uuid
from typing import Any

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_usage_record import AiUsageRecord
from app.research.citations import Meta
from app.research.claims import LoadedPaper, StoredClaim
from app.research.drafts import (
    check_sentences,
    cited_ids,
    marker,
    render_markdown,
    split_sentences,
)
from app.research.writing_assist import apply_numbers, to_numbered
from tests.research.test_comparisons import RESULT_A, analysed_paper
from tests.research.test_projects_api import make as make_project
from tests.retrieval.test_search import Actor
from tests.study.conftest import Harness
from tests.test_closeout_users_config import _call

PID = uuid.UUID("11111111-1111-1111-1111-111111111111")
OTHER = uuid.UUID("22222222-2222-2222-2222-222222222222")


def loaded(pid: uuid.UUID, *texts: str) -> LoadedPaper:
    claims = [
        StoredClaim(pid, "results", i, None, t, "reported", None, "q", 1, None)
        for i, t in enumerate(texts)
    ]
    return LoadedPaper(pid, "Paper", 2020, uuid.uuid4(), 1, claims)


class TestPure:
    def test_markers_round_trip_and_order(self) -> None:
        text = f"A {marker(PID)} and B {marker(OTHER)} again {marker(PID)}."
        assert cited_ids(text) == [PID, OTHER]
        assert cited_ids("no markers {{cite:not-a-uuid}}") == []

    def test_sentences_skip_headings_and_bullets_markers(self) -> None:
        text = "# Heading\n\nFirst sentence. Second one here.\n- A bullet point.\n"
        assert split_sentences(text) == ["First sentence.", "Second one here.", "A bullet point."]

    def test_check_statuses(self) -> None:
        paper = loaded(PID, "Chloroplasts turn light into chemical energy.")
        text = (
            f"Chloroplasts convert light into chemical energy {marker(PID)}. "
            "Accuracy improved by 40%. "
            "This is a plain transition. "
            f"Mitochondria oxidise acetyl groups {marker(PID)}. "
            f"Anything {marker(uuid.uuid4())}. "
            f"Chloroplasts and light {marker(OTHER)}."
        )
        checks = check_sentences(text, {PID, OTHER}, {PID: paper})
        assert [c.status for c in checks] == [
            "supported_single",
            "unsupported",
            "unmarked",
            "citation_mismatch",
            "invalid_reference",
            "cannot_verify",
        ]

    def test_two_matching_papers_are_supported_by_multiple(self) -> None:
        a = loaded(PID, "Chloroplasts turn light into chemical energy.")
        b = loaded(OTHER, "Chloroplasts absorb light to make chemical energy.")
        text = f"Chloroplasts use light for chemical energy {marker(PID)}{marker(OTHER)}."
        checks = check_sentences(text, {PID, OTHER}, {PID: a, OTHER: b})
        assert checks[0].status == "supported_multiple"

    def test_render_resolves_citations_and_generates_references(self) -> None:
        meta = Meta(authors=("Smith, John",), title="A paper", year=2020, venue="J. Bio")
        content = f"## Intro\n\nChloroplasts matter {marker(PID)}.\n\n## References\n\nold text\n"
        apa = render_markdown("My draft", content, {PID: meta}, "apa")
        assert "(Smith, 2020)" in apa.markdown and "old text" not in apa.markdown
        assert (
            apa.markdown.count("## References") == 1
            and "Smith, J. (2020). A paper." in apa.markdown
        )
        ieee = render_markdown("My draft", content, {PID: meta}, "ieee")
        assert "[1]" in ieee.markdown and "[1] J. Smith" in ieee.markdown
        missing = render_markdown("T", f"X {marker(OTHER)}.", {}, "apa")
        assert missing.invalid == [OTHER] and "[unknown reference]" in missing.markdown

    def test_numbers_map_back_to_papers_and_unknown_numbers_are_dropped(self) -> None:
        text, bad = apply_numbers("Claim [1]. Other [2, 9]. Gone [7].", {1: PID, 2: OTHER})
        assert bad == 2
        assert marker(PID) in text and marker(OTHER) in text and "[7]" not in text
        assert to_numbered(f"x {marker(PID)}", [PID]) == "x [1]"


async def new_draft(client: AsyncClient, who: Actor, pid: str, **kw: Any) -> dict[str, Any]:
    resp = await _call(
        client,
        who,
        "POST",
        f"/research/projects/{pid}/drafts",
        json={"title": "My draft", "content": "First version.", **kw},
    )
    assert resp.status_code == 201, resp.text
    data: dict[str, Any] = resp.json()["data"]
    return data


class TestVersions:
    async def test_edit_creates_versions_and_conflicts_are_refused(
        self, client: AsyncClient, alice: Actor
    ) -> None:
        pid = (await make_project(client, alice))["id"]
        draft = await new_draft(client, alice, pid)
        assert draft["version_number"] == 1 and draft["word_count"] == 2
        url = f"/research/drafts/{draft['id']}"
        no_version = await _call(client, alice, "PATCH", url, json={"content": "x"})
        assert no_version.status_code == 422
        saved = await _call(
            client, alice, "PATCH", url, json={"content": "Second.", "expected_version": 1}
        )
        assert saved.status_code == 200 and saved.json()["data"]["version_number"] == 2
        stale = await _call(
            client, alice, "PATCH", url, json={"content": "Lost.", "expected_version": 1}
        )
        assert stale.status_code == 409
        assert stale.json()["error"]["code"] == "RESEARCH_DRAFT_VERSION_CONFLICT"
        same = await _call(
            client, alice, "PATCH", url, json={"content": "Second.", "expected_version": 2}
        )
        assert same.json()["data"]["version_number"] == 2  # unchanged text: no new version
        status = await _call(client, alice, "PATCH", url, json={"status": "in_review"})
        assert status.json()["data"]["status"] == "in_review"
        versions = (await _call(client, alice, "GET", f"{url}/versions")).json()["data"]
        assert [v["version_number"] for v in versions] == [2, 1]
        assert [v["change_source"] for v in versions] == ["manual", "created"]

    async def test_restore_adds_a_version_and_never_rewrites_history(
        self, client: AsyncClient, alice: Actor
    ) -> None:
        pid = (await make_project(client, alice))["id"]
        draft = await new_draft(client, alice, pid)
        url = f"/research/drafts/{draft['id']}"
        await _call(
            client, alice, "PATCH", url, json={"content": "Changed.", "expected_version": 1}
        )
        old = await _call(client, alice, "GET", f"{url}/versions/1")
        assert old.json()["data"]["content"] == "First version."
        bad = await _call(
            client, alice, "POST", f"{url}/versions/1/restore", json={"expected_version": 1}
        )
        assert bad.status_code == 409
        restored = await _call(
            client, alice, "POST", f"{url}/versions/1/restore", json={"expected_version": 2}
        )
        data = restored.json()["data"]
        assert data["content"] == "First version." and data["version_number"] == 3
        versions = (await _call(client, alice, "GET", f"{url}/versions")).json()["data"]
        assert [v["change_source"] for v in versions] == ["restore", "manual", "created"]
        assert (await _call(client, alice, "GET", f"{url}/versions/9")).status_code == 404

    async def test_ai_accepted_edit_is_marked_and_other_users_see_404(
        self, client: AsyncClient, alice: Actor, bob: Actor
    ) -> None:
        pid = (await make_project(client, alice))["id"]
        draft = await new_draft(client, alice, pid)
        url = f"/research/drafts/{draft['id']}"
        resp = await _call(
            client,
            alice,
            "PATCH",
            url,
            json={"content": "AI text.", "expected_version": 1, "change_source": "ai_suggestion"},
        )
        versions = (await _call(client, alice, "GET", f"{url}/versions")).json()["data"]
        assert versions[0]["change_source"] == "ai_suggestion"
        assert versions[0]["change_summary"] == "AI suggestion accepted" and resp.status_code == 200
        calls: list[tuple[str, str, dict[str, Any] | None]] = [
            ("POST", f"/research/projects/{pid}/drafts", {"title": "x"}),
            ("GET", f"/research/projects/{pid}/drafts", None),
            ("GET", url, None),
            ("PATCH", url, {"status": "final"}),
            ("DELETE", url, None),
            ("GET", f"{url}/versions", None),
            ("GET", f"{url}/versions/1", None),
            ("POST", f"{url}/versions/1/restore", {"expected_version": 2}),
            ("POST", f"{url}/check", None),
            ("GET", f"{url}/preview", None),
            ("GET", f"{url}/export", None),
            ("POST", f"{url}/assist", {"action": "grammar", "selected_text": "x"}),
        ]
        for method, path, body in calls:
            r = await _call(client, bob, method, path, json=body)
            assert r.status_code == 404, (method, path, r.status_code)
        assert (await _call(client, alice, "DELETE", url)).status_code == 204


class TestCheckAndExport:
    async def test_check_and_export_use_the_projects_papers(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, lab: Harness
    ) -> None:
        pid = (await make_project(client, alice))["id"]
        paper = await analysed_paper(
            client, db_session, alice, lab, pid, "Paper A", results=[RESULT_A]
        )
        await _call(
            client,
            alice,
            "PATCH",
            f"/research/papers/{paper}",
            json={"authors": ["Smith, John"], "publication_year": 2020, "venue": "J. Bio"},
        )
        content = (
            "## Results\n\nChloroplasts turn light into chemical energy "
            f"{marker(uuid.UUID(paper))}. Accuracy improved by 40%."
        )
        draft = await new_draft(client, alice, pid, content=content)
        url = f"/research/drafts/{draft['id']}"
        report = (await _call(client, alice, "POST", f"{url}/check")).json()["data"]
        assert [c["status"] for c in report["checks"]] == ["supported_single", "unsupported"]
        assert report["summary"]["unsupported"] == 1 and report["invalid_references"] == []
        exported = (await _call(client, alice, "GET", f"{url}/export")).json()["data"]
        assert exported["filename"] == "My_draft.md" and exported["cited_count"] == 1
        assert "(Smith, 2020)" in exported["content"] and "## References" in exported["content"]
        # a dangling citation: preview works, export is refused
        dangling = f"Text {marker(uuid.uuid4())}."
        await _call(client, alice, "PATCH", url, json={"content": dangling, "expected_version": 1})
        preview = (await _call(client, alice, "GET", f"{url}/preview")).json()["data"]
        assert "[unknown reference]" in preview["content"] and preview["invalid_references"]
        refused = await _call(client, alice, "GET", f"{url}/export")
        assert refused.status_code == 422
        assert refused.json()["error"]["code"] == "RESEARCH_DRAFT_INVALID_REFERENCES"


def assist_reply(text: str, notes: str = "") -> str:
    return json.dumps({"text": text, "notes": notes})


class TestAssist:
    async def usage_rows(self, db: AsyncSession) -> int:
        stmt = select(func.count(AiUsageRecord.id)).where(
            AiUsageRecord.request_kind == "research_writing"
        )
        return int((await db.execute(stmt)).scalar_one())

    async def test_grounded_section_maps_markers_and_flags_unsupported_claims(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, lab: Harness
    ) -> None:
        pid = (await make_project(client, alice))["id"]
        paper = await analysed_paper(
            client, db_session, alice, lab, pid, "Paper A", results=[RESULT_A]
        )
        draft = await new_draft(client, alice, pid)
        lab.provider.reply = assist_reply(
            "Chloroplasts convert light energy into chemical energy [1]. "
            "We interpret this as a basis for later work. "
            "The yield improved by 40% [99].",
            "Only one source was available.",
        )
        before = await self.usage_rows(db_session)
        resp = await _call(
            client,
            alice,
            "POST",
            f"/research/drafts/{draft['id']}/assist",
            json={"action": "draft_section", "section": "results"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert marker(uuid.UUID(paper)) in data["text"] and "[99]" not in data["text"]
        assert data["invalid_markers"] == 1
        assert [s["paper_id"] for s in data["sources"]] == [paper]
        assert data["sources"][0]["quote"]
        statuses = [c["status"] for c in data["checks"]]
        assert statuses == ["supported_single", "unmarked", "unsupported"]
        assert data["unsupported_count"] == 1 and data["notes"] == "Only one source was available."
        assert await self.usage_rows(db_session) == before + 1
        # a suggestion is never saved
        saved = (await _call(client, alice, "GET", f"/research/drafts/{draft['id']}")).json()[
            "data"
        ]
        assert saved["content"] == "First version." and saved["version_number"] == 1

    async def test_edit_action_keeps_existing_citations(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, lab: Harness
    ) -> None:
        pid = (await make_project(client, alice))["id"]
        paper = await analysed_paper(
            client, db_session, alice, lab, pid, "Paper A", results=[RESULT_A]
        )
        text = f"Chloroplasts turn light into chemical energy {marker(uuid.UUID(paper))}."
        draft = await new_draft(client, alice, pid, content=text)
        lab.provider.reply = assist_reply("Chloroplasts convert light into chemical energy [1].")
        resp = await _call(
            client,
            alice,
            "POST",
            f"/research/drafts/{draft['id']}/assist",
            json={"action": "clarity", "selected_text": text},
        )
        data = resp.json()["data"]
        assert resp.status_code == 200, resp.text
        assert marker(uuid.UUID(paper)) in data["text"] and data["sources"] == []
        assert data["checks"][0]["status"] == "supported_single"

    async def test_input_and_evidence_requirements(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, lab: Harness
    ) -> None:
        pid = (await make_project(client, alice))["id"]
        draft = await new_draft(client, alice, pid)
        url = f"/research/drafts/{draft['id']}/assist"
        no_text = await _call(client, alice, "POST", url, json={"action": "rewrite"})
        assert no_text.status_code == 422
        no_evidence = await _call(
            client, alice, "POST", url, json={"action": "draft_section", "section": "results"}
        )
        assert no_evidence.status_code == 422
        bad = await _call(client, alice, "POST", url, json={"action": "write_my_thesis"})
        assert bad.status_code == 422

    async def test_unusable_output_is_an_error_not_a_made_up_text(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, lab: Harness
    ) -> None:
        pid = (await make_project(client, alice))["id"]
        await analysed_paper(client, db_session, alice, lab, pid, "Paper A", results=[RESULT_A])
        draft = await new_draft(client, alice, pid)
        lab.provider.reply = "not json at all"
        resp = await _call(
            client,
            alice,
            "POST",
            f"/research/drafts/{draft['id']}/assist",
            json={"action": "draft_section", "section": "results"},
        )
        assert resp.status_code == 502
        assert resp.json()["error"]["code"] == "RESEARCH_WRITING_OUTPUT_INVALID"
