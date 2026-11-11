"""Phase 4 M5: study library, preferences, versions/regeneration, exports. No network, no cost."""

import csv
import io
import json
import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.main import app
from app.models.document import Document
from app.models.storage_cleanup import StorageCleanup
from app.models.study_export import StudyExport
from app.models.study_material import StudyMaterial
from app.modules.study.library_routes import get_export_storage
from app.repositories.flashcard_repository import FlashcardRepository
from app.repositories.quiz_repository import QuizRepository
from app.repositories.study_material_repository import StudyMaterialRepository
from app.storage.memory_backend import InMemoryStorageBackend
from app.study.dispatch import get_export_dispatcher
from app.study.export_runner import expire_exports, run_export
from app.study.exporting import (
    ExportInput,
    csv_safe,
    md_escape,
    render_csv,
    render_markdown,
    render_pdf,
)
from tests.conftest import _TestSessionLocal
from tests.retrieval.test_search import Actor, add_doc
from tests.study.conftest import Harness
from tests.test_closeout_users_config import PASSWORD, _call

try:  # parsers live only in the worker image (D-70); PDF/DOCX checks skip where they are absent
    import pymupdf
except ImportError:  # pragma: no cover
    pymupdf = None  # type: ignore[assignment]


def need_pdf() -> None:
    if pymupdf is None:
        pytest.skip("pymupdf is only installed in the worker image")


def need_docx() -> None:
    pytest.importorskip("docx")


LONG = "word " * 100
PAYLOADS: dict[str, dict[str, Any]] = {
    "summary": {
        "title": "Cell summary",
        "sections": [{"heading": "Intro", "body": "Cells make energy.", "bullets": ["ATP"]}],
    },
    "study_guide": {
        "title": "Guide",
        "overview": "Overview text.",
        "learning_objectives": [{"text": "Explain ATP"}],
        "prerequisites": ["Chemistry"],
        "sections": [{"heading": "Part", "level": 1, "body": "Body", "bullets": []}],
        "key_takeaways": ["Remember ATP"],
        "practice_questions": [{"question": "What is ATP?"}],
    },
    "glossary": {
        "title": "Terms",
        "terms": [
            {
                "term": "ATP",
                "definition": "Energy currency",
                "explanation": "",
                "example": "",
                "topic": "Energy",
                "related_terms": ["ADP"],
            }
        ],
    },
    "formula_sheet": {
        "title": "Formulas",
        "formulas": [
            {
                "name": "Energy",
                "expression": "E = mc^2",
                "explanation": "",
                "variables": [{"symbol": "E", "meaning": "energy", "unit": "J"}],
            }
        ],
    },
    "question_bank": {
        "title": "Bank",
        "questions": [
            {
                "question": "What makes ATP?",
                "question_type": "multiple_choice",
                "difficulty": "easy",
                "topic": "Energy",
                "options": [{"id": "A", "text": "Mitochondria"}, {"id": "B", "text": "Nucleus"}],
            }
        ],
    },
}


class ExportRecorder:
    def __init__(self) -> None:
        self.sent: list[uuid.UUID] = []
        self.is_available = True

    def available(self) -> bool:
        return self.is_available

    def dispatch(self, export_id: uuid.UUID) -> bool:
        self.sent.append(export_id)
        return True


@pytest.fixture
def exports() -> Generator[tuple[ExportRecorder, InMemoryStorageBackend]]:
    recorder, storage = ExportRecorder(), InMemoryStorageBackend("testing")  # type: ignore[arg-type]
    app.dependency_overrides[get_export_dispatcher] = lambda: recorder
    app.dependency_overrides[get_export_storage] = lambda: storage
    yield recorder, storage
    app.dependency_overrides.pop(get_export_dispatcher, None)
    app.dependency_overrides.pop(get_export_storage, None)


async def commit(db: AsyncSession) -> None:
    """Commit without expiring loaded objects (the actors are reused afterwards)."""
    db.sync_session.expire_on_commit = False
    await db.commit()


async def make_material(
    db: AsyncSession,
    who: Actor,
    kind: str,
    payload: dict[str, Any] | None = None,
    *,
    title: str | None = None,
    documents: list[uuid.UUID] | None = None,
    subject: bool = True,
) -> StudyMaterial:
    body = payload if payload is not None else PAYLOADS.get(kind, {"title": "T"})
    row = await StudyMaterialRepository(db).create_with_first_version(
        user_id=who.user.id,
        workspace_id=who.ws.id,
        subject_id=who.subject.id if subject else None,
        chapter_id=None,
        title=title or str(body.get("title", "T")),
        resource_type=kind,
        status="completed",
        content={"payload": body, "sources": []},
        generation_settings={},
        source_metadata={"documents": [str(d) for d in documents or []]},
    )
    await commit(db)
    return row


async def make_deck(db: AsyncSession, who: Actor, fronts: list[str]) -> StudyMaterial:
    material = await make_material(db, who, "flashcards", {"title": "Deck"})
    repo = FlashcardRepository(db)
    card_set = await repo.create_set(who.user.id, material.id)
    await repo.add_cards(
        card_set,
        [
            {
                "front": f,
                "back": "=HYPERLINK(" + '"http://evil"' + ")",
                "card_type": "basic",
                "difficulty": "easy",
                "origin": "manual",
            }
            for f in fronts
        ],
    )
    await commit(db)
    return material


async def make_quiz(db: AsyncSession, who: Actor) -> StudyMaterial:
    material = await make_material(db, who, "quiz", {"title": "Quiz", "description": "d"})
    await QuizRepository(db).create_quiz(
        user_id=who.user.id,
        material_id=material.id,
        title="Quiz",
        description=None,
        time_limit=None,
        settings={},
        questions=[
            {
                "question": "Pick the powerhouse",
                "question_type": "multiple_choice",
                "difficulty": "easy",
                "options": [{"id": "A", "text": "Mitochondria"}, {"id": "B", "text": "Nucleus"}],
                "correct_answers": ["A"],
                "rubric": [],
                "explanation": "SECRET-EXPLANATION",
                "source_references": [],
            }
        ],
    )
    await commit(db)
    return material


async def export_file(
    client: AsyncClient,
    who: Actor,
    exports: tuple[ExportRecorder, InMemoryStorageBackend],
    material_id: uuid.UUID,
    fmt: str,
) -> tuple[str, bytes]:
    if fmt == "pdf":
        need_pdf()
    if fmt == "docx":
        need_docx()
    resp = await _call(
        client, who, "POST", f"/study/materials/{material_id}/export", json={"format": fmt}
    )
    assert resp.status_code == 202, resp.text
    export_id = resp.json()["data"]["id"]
    assert resp.json()["data"]["status"] == "pending"
    assert await run_export(
        _TestSessionLocal, exports[1], get_settings(), uuid.UUID(export_id)
    ) == ("completed")
    done = (await _call(client, who, "GET", f"/study/exports/{export_id}")).json()["data"]
    assert done["status"] == "completed" and done["download_path"]
    dl = await _call(client, who, "GET", f"/study/exports/{export_id}/download")
    assert dl.status_code == 200, dl.text
    return export_id, dl.content


# library ───────────────────────────────────────────────────────────────────


class TestLibrary:
    async def test_list_filters_search_sort_and_pagination(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor
    ) -> None:
        await make_material(db_session, alice, "summary", title="Photosynthesis notes")
        await make_material(db_session, alice, "glossary", title="Cell terms")
        await make_material(db_session, alice, "glossary", title="100%_literal")
        got = await _call(client, alice, "GET", "/study/materials")
        assert got.status_code == 200 and got.json()["total"] == 3
        item = got.json()["data"][0]
        assert "content" not in item and "payload" not in json.dumps(item)

        by_type = await _call(client, alice, "GET", "/study/materials?resource_type=glossary")
        assert by_type.json()["total"] == 2
        by_title = await _call(client, alice, "GET", "/study/materials?q=photosynth")
        assert [m["title"] for m in by_title.json()["data"]] == ["Photosynthesis notes"]
        # search reaches the stored content too
        by_body = await _call(client, alice, "GET", "/study/materials?q=Cells make energy")
        assert by_body.json()["total"] == 1
        # LIKE wildcards are literal
        assert (await _call(client, alice, "GET", "/study/materials?q=%25_")).json()["total"] == 1
        assert (await _call(client, alice, "GET", "/study/materials?q=%25")).json()["total"] == 1
        by_subject = await _call(
            client, alice, "GET", f"/study/materials?subject_id={alice.subject.id}"
        )
        assert by_subject.json()["total"] == 3
        by_ws = await _call(client, alice, "GET", f"/study/materials?workspace_id={alice.ws.id}")
        assert by_ws.json()["total"] == 3
        none = await _call(client, alice, "GET", f"/study/materials?chapter_id={uuid.uuid4()}")
        assert none.json()["total"] == 0
        assert (await _call(client, alice, "GET", "/study/materials?status=failed")).json()[
            "total"
        ] == 0

        titles = await _call(client, alice, "GET", "/study/materials?sort=title&order=asc")
        names = [m["title"] for m in titles.json()["data"]]
        assert names == sorted(names)
        page = await _call(client, alice, "GET", "/study/materials?limit=2&offset=2")
        assert len(page.json()["data"]) == 1 and page.json()["total"] == 3

    async def test_bad_sort_and_limit_rejected(self, client: AsyncClient, alice: Actor) -> None:
        for bad in ("sort=content", "sort=user_id;drop", "limit=1000", "limit=0", "offset=-1"):
            resp = await _call(client, alice, "GET", f"/study/materials?{bad}")
            assert resp.status_code == 422, bad
        assert (await _call(client, alice, "GET", "/study/materials?q=%27%20OR%201%3D1--")).json()[
            "total"
        ] == 0

    async def test_list_is_isolated_between_users(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, bob: Actor
    ) -> None:
        await make_material(db_session, alice, "summary", title="Alice only")
        assert (await _call(client, bob, "GET", "/study/materials")).json()["total"] == 0
        # Bob filtering by Alice's ids still sees nothing
        resp = await _call(client, bob, "GET", f"/study/materials?subject_id={alice.subject.id}")
        assert resp.json()["total"] == 0

    async def test_archive_unarchive_and_default_hides_archived(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor
    ) -> None:
        m = await make_material(db_session, alice, "summary")
        resp = await _call(client, alice, "POST", f"/study/materials/{m.id}/archive")
        assert resp.status_code == 200 and resp.json()["data"]["archived_at"]
        assert (await _call(client, alice, "GET", "/study/materials")).json()["total"] == 0
        only = await _call(client, alice, "GET", "/study/materials?archived=only")
        assert only.json()["total"] == 1
        assert (await _call(client, alice, "GET", "/study/materials?archived=all")).json()[
            "total"
        ] == 1
        back = await _call(client, alice, "POST", f"/study/materials/{m.id}/unarchive")
        assert back.json()["data"]["archived_at"] is None

    async def test_duplicate_is_independent_copy(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor
    ) -> None:
        m = await make_material(db_session, alice, "summary")
        resp = await _call(client, alice, "POST", f"/study/materials/{m.id}/duplicate")
        assert resp.status_code == 201
        copy = resp.json()["data"]
        assert copy["id"] != str(m.id) and copy["title"].endswith("(copy)")
        assert copy["current_version"] == 1
        edited = {**PAYLOADS["summary"], "title": "Changed"}
        patch = await _call(
            client,
            alice,
            "PATCH",
            f"/study/materials/{copy['id']}",
            json={"expected_version": 1, "payload": edited},
        )
        assert patch.status_code == 200, patch.text
        original = (await _call(client, alice, "GET", f"/study/materials/{m.id}")).json()["data"]
        assert original["title"] == "Cell summary" and original["current_version"] == 1

    async def test_duplicate_flashcards_copies_cards_and_quiz_is_refused(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor
    ) -> None:
        deck = await make_deck(db_session, alice, ["Front one?", "Front two?"])
        resp = await _call(client, alice, "POST", f"/study/materials/{deck.id}/duplicate")
        assert resp.status_code == 201
        new_id = uuid.UUID(resp.json()["data"]["id"])
        repo = FlashcardRepository(db_session)
        copied = await repo.get_set_for_material(new_id, alice.user.id)
        assert copied is not None
        assert len(await repo.cards(copied.id, alice.user.id)) == 2
        quiz = await make_quiz(db_session, alice)
        refused = await _call(client, alice, "POST", f"/study/materials/{quiz.id}/duplicate")
        assert refused.status_code == 422
        assert refused.json()["error"]["code"] == "DUPLICATE_NOT_SUPPORTED"

    async def test_delete_cascades_versions_and_cards(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor
    ) -> None:
        deck = await make_deck(db_session, alice, ["Front one?"])
        deck_id, uid = deck.id, alice.user.id
        assert (
            await _call(client, alice, "DELETE", f"/study/materials/{deck_id}")
        ).status_code == 204
        assert (await _call(client, alice, "GET", f"/study/materials/{deck_id}")).status_code == 404
        db_session.expire_all()
        repo = FlashcardRepository(db_session)
        assert await repo.get_set_for_material(deck_id, uid) is None
        assert await StudyMaterialRepository(db_session).versions(deck_id, uid) == []

    async def test_foreign_ids_are_404_on_every_route(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, bob: Actor
    ) -> None:
        m = await make_material(db_session, alice, "summary")
        for method, url, body in (
            ("DELETE", f"/study/materials/{m.id}", None),
            ("POST", f"/study/materials/{m.id}/duplicate", None),
            ("POST", f"/study/materials/{m.id}/archive", None),
            ("POST", f"/study/materials/{m.id}/unarchive", None),
            ("POST", f"/study/materials/{m.id}/export", {"format": "pdf"}),
            ("POST", f"/study/materials/{m.id}/regenerate", {}),
            ("POST", f"/study/materials/{m.id}/restore", {"expected_version": 1, "version": 1}),
            ("GET", f"/study/materials/{m.id}/versions", None),
        ):
            resp = (
                await _call(client, bob, method, url, json=body)
                if body is not None
                else (await _call(client, bob, method, url))
            )
            assert resp.status_code == 404, (method, url, resp.text)
        assert (await _call(client, alice, "GET", f"/study/materials/{m.id}")).status_code == 200

    async def test_requires_login(self, client: AsyncClient) -> None:
        for method, url in (
            ("GET", "/study/materials"),
            ("GET", "/study/preferences"),
            ("GET", f"/study/exports/{uuid.uuid4()}"),
        ):
            assert (await client.request(method, f"/api/v1{url}")).status_code == 401

    async def test_deleting_source_document_keeps_material_and_marks_reference(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor
    ) -> None:
        doc = await add_doc(db_session, alice, "Bio", ["Some text. " + LONG])
        doc_id = doc.id
        m = await make_material(db_session, alice, "summary", documents=[doc_id])
        material_id = m.id
        item = (await _call(client, alice, "GET", "/study/materials")).json()["data"][0]
        assert item["source_document_count"] == 1 and item["unavailable_source_count"] == 0
        from app.modules.documents.routes import get_document_storage

        app.dependency_overrides[get_document_storage] = lambda: InMemoryStorageBackend("testing")  # type: ignore[arg-type]
        try:
            resp = await _call(client, alice, "DELETE", f"/documents/{doc_id}")
        finally:
            app.dependency_overrides.pop(get_document_storage, None)
        assert resp.status_code in (200, 204), resp.text
        db_session.expire_all()
        assert (await db_session.get(Document, doc_id)) is None
        got = (await _call(client, alice, "GET", f"/study/materials/{material_id}")).json()["data"]
        assert got["unavailable_document_ids"] == [str(doc_id)]
        item = (await _call(client, alice, "GET", "/study/materials")).json()["data"][0]
        assert item["unavailable_source_count"] == 1


# versions and regeneration (D-92) ──────────────────────────────────────────


class TestVersions:
    async def test_edit_restore_keeps_original_and_numbers(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor
    ) -> None:
        m = await make_material(db_session, alice, "summary")
        edited = {**PAYLOADS["summary"], "title": "Edited title"}
        r = await _call(
            client,
            alice,
            "PATCH",
            f"/study/materials/{m.id}",
            json={"expected_version": 1, "payload": edited},
        )
        assert r.status_code == 200 and r.json()["data"]["current_version"] == 2
        stale = await _call(
            client,
            alice,
            "PATCH",
            f"/study/materials/{m.id}",
            json={"expected_version": 1, "payload": edited},
        )
        assert stale.status_code == 409
        restored = await _call(
            client,
            alice,
            "POST",
            f"/study/materials/{m.id}/restore",
            json={"expected_version": 2, "version": 1},
        )
        data = restored.json()["data"]
        assert data["current_version"] == 3 and data["title"] == "Cell summary"
        versions = (await _call(client, alice, "GET", f"/study/materials/{m.id}/versions")).json()
        assert [(v["version_number"], v["origin"]) for v in versions["data"]] == [
            (1, "generated"),
            (2, "edited"),
            (3, "restored"),
        ]
        v2 = await _call(client, alice, "GET", f"/study/materials/{m.id}/versions/2")
        assert v2.json()["data"]["content"]["payload"]["title"] == "Edited title"

    async def test_regenerate_previews_and_never_overwrites_edits(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, study: Harness
    ) -> None:
        doc = await add_doc(db_session, alice, "Bio", ["Photosynthesis. " + LONG])
        m = await make_material(db_session, alice, "summary", documents=[doc.id])
        await db_session.execute(
            update(StudyMaterial)
            .where(StudyMaterial.id == m.id)
            .values(source_metadata={"source": {"type": "document", "id": str(doc.id)}})
        )
        await db_session.commit()
        study.provider.reply = json.dumps(
            {"title": "New take", "sections": [{"heading": "Fresh", "body": "New body"}]}
        )
        resp = await _call(client, alice, "POST", f"/study/materials/{m.id}/regenerate", json={})
        assert resp.status_code == 202, resp.text
        job_id = resp.json()["data"]["id"]
        await study.run(job_id)
        preview = (await _call(client, alice, "GET", f"/study/generations/{job_id}/preview")).json()
        assert preview["data"]["stale"] is False
        # the live material is untouched while only a preview exists
        live = (await _call(client, alice, "GET", f"/study/materials/{m.id}")).json()["data"]
        assert live["title"] == "Cell summary" and live["current_version"] == 1
        # an edit made meanwhile makes the preview stale: applying is refused
        edited = {**PAYLOADS["summary"], "title": "My edit"}
        await _call(
            client,
            alice,
            "PATCH",
            f"/study/materials/{m.id}",
            json={"expected_version": 1, "payload": edited},
        )
        applied = await _call(client, alice, "POST", f"/study/generations/{job_id}/preview/apply")
        assert applied.status_code == 409
        assert applied.json()["error"]["code"] == "PREVIEW_STALE"
        final = (await _call(client, alice, "GET", f"/study/materials/{m.id}")).json()["data"]
        assert final["title"] == "My edit"


# preferences ───────────────────────────────────────────────────────────────


class TestPreferences:
    async def test_roundtrip_validation_and_isolation(
        self, client: AsyncClient, alice: Actor, bob: Actor
    ) -> None:
        empty = (await _call(client, alice, "GET", "/study/preferences")).json()["data"]
        assert empty["language"] is None and empty["include_examples"] is True
        body = {
            "language": "French",
            "explanation_level": "beginner",
            "summary_length": "short",
            "question_difficulty": "hard",
            "include_examples": False,
            "include_definitions": True,
            "include_source_references": False,
        }
        saved = await _call(client, alice, "PUT", "/study/preferences", json=body)
        assert saved.status_code == 200 and saved.json()["data"] == body
        assert (await _call(client, alice, "GET", "/study/preferences")).json()["data"] == body
        assert (await _call(client, bob, "GET", "/study/preferences")).json()["data"][
            "language"
        ] is None
        for bad in ({"explanation_level": "expert"}, {"language": "x" * 40}, {"extra": 1}):
            assert (
                await _call(client, alice, "PUT", "/study/preferences", json=bad)
            ).status_code == 422
        cleared = await _call(client, alice, "PUT", "/study/preferences", json={})
        assert cleared.json()["data"]["language"] is None

    async def test_used_as_generation_defaults_but_request_wins(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, study: Harness
    ) -> None:
        doc = await add_doc(db_session, alice, "Bio", ["Photosynthesis. " + LONG])
        await _call(
            client,
            alice,
            "PUT",
            "/study/preferences",
            json={"language": "French", "summary_length": "short", "include_examples": True},
        )
        body: dict[str, Any] = {
            "generation_type": "summary",
            "source": {"type": "document", "id": str(doc.id)},
            "settings": {},
        }
        first = await _call(client, alice, "POST", "/study/generations", json=body)
        assert first.status_code == 202, first.text
        job_id = uuid.UUID(first.json()["data"]["id"])
        from app.models.generation_job import GenerationJob

        db_session.expire_all()
        job = await db_session.get(GenerationJob, job_id)
        assert job is not None
        used = job.request["settings"]
        assert used["language"] == "French"
        assert used["detail_level"] == "brief"
        assert used["include_examples"] is True
        body["settings"] = {"language": "German"}
        second = await _call(client, alice, "POST", "/study/generations", json=body)
        job2 = await db_session.get(GenerationJob, uuid.UUID(second.json()["data"]["id"]))
        assert job2 is not None and job2.request["settings"]["language"] == "German"


# exports ───────────────────────────────────────────────────────────────────


class TestExports:
    @pytest.mark.parametrize(
        ("kind", "fmt"),
        [
            ("summary", "pdf"),
            ("summary", "docx"),
            ("summary", "md"),
            ("study_guide", "pdf"),
            ("study_guide", "docx"),
            ("glossary", "csv"),
            ("glossary", "pdf"),
            ("formula_sheet", "pdf"),
            ("question_bank", "csv"),
            ("question_bank", "pdf"),
        ],
    )
    async def test_each_resource_type_and_format(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        alice: Actor,
        exports: tuple[ExportRecorder, InMemoryStorageBackend],
        kind: str,
        fmt: str,
    ) -> None:
        m = await make_material(db_session, alice, kind)
        export_id, data = await export_file(client, alice, exports, m.id, fmt)
        assert exports[0].sent[-1] == uuid.UUID(export_id)
        if fmt == "pdf":
            assert data.startswith(b"%PDF")
            text = "".join(p.get_text() for p in pymupdf.open(stream=data, filetype="pdf"))
            assert PAYLOADS[kind]["title"] in text
        elif fmt == "docx":
            assert data.startswith(b"PK")
        elif fmt == "csv":
            rows = list(csv.reader(io.StringIO(data.decode("utf-8"))))
            assert len(rows) == 2
        else:
            assert data.decode().startswith("# ")

    async def test_flashcards_csv_neutralises_formulas_and_pdf_works(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        alice: Actor,
        exports: tuple[ExportRecorder, InMemoryStorageBackend],
    ) -> None:
        deck = await make_deck(db_session, alice, ["+SUM(1,1) front?", "Plain front?"])
        _, data = await export_file(client, alice, exports, deck.id, "csv")
        rows = list(csv.reader(io.StringIO(data.decode("utf-8"))))
        assert rows[0][:2] == ["front", "back"]
        for row in rows[1:]:
            for cell in row:
                assert not cell.startswith(("=", "+", "-", "@", "\t", "\r"))
        assert rows[1][1].startswith("'=HYPERLINK")
        _, pdf = await export_file(client, alice, exports, deck.id, "pdf")
        assert pdf.startswith(b"%PDF")

    async def test_quiz_export_never_contains_answer_key(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        alice: Actor,
        exports: tuple[ExportRecorder, InMemoryStorageBackend],
    ) -> None:
        quiz = await make_quiz(db_session, alice)
        _, pdf = await export_file(client, alice, exports, quiz.id, "pdf")
        text = "".join(p.get_text() for p in pymupdf.open(stream=pdf, filetype="pdf"))
        assert "Pick the powerhouse" in text and "Mitochondria" in text
        assert "SECRET-EXPLANATION" not in text
        assert "correct" not in text.lower()
        bank_view = render_csv(
            ExportInput("question_bank", "B", PAYLOADS["question_bank"], [], [])
        ).decode()
        assert "correct" not in bank_view.lower()

    async def test_unsupported_format_and_unknown_material(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        alice: Actor,
        exports: tuple[ExportRecorder, InMemoryStorageBackend],
    ) -> None:
        quiz = await make_quiz(db_session, alice)
        csv_quiz = await _call(
            client, alice, "POST", f"/study/materials/{quiz.id}/export", json={"format": "csv"}
        )
        assert csv_quiz.status_code == 422
        assert csv_quiz.json()["error"]["code"] == "EXPORT_FORMAT_UNSUPPORTED"
        bad = await _call(
            client, alice, "POST", f"/study/materials/{quiz.id}/export", json={"format": "exe"}
        )
        assert bad.status_code == 422
        missing = await _call(
            client,
            alice,
            "POST",
            f"/study/materials/{uuid.uuid4()}/export",
            json={"format": "md"},
        )
        assert missing.status_code == 404

    async def test_foreign_export_status_and_download_are_404(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        alice: Actor,
        bob: Actor,
        exports: tuple[ExportRecorder, InMemoryStorageBackend],
    ) -> None:
        m = await make_material(db_session, alice, "summary")
        export_id, _ = await export_file(client, alice, exports, m.id, "md")
        for url in (f"/study/exports/{export_id}", f"/study/exports/{export_id}/download"):
            assert (await _call(client, bob, "GET", url)).status_code == 404
            assert (await client.get(f"/api/v1{url}")).status_code == 401

    async def test_download_headers_and_pending_not_ready(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        alice: Actor,
        exports: tuple[ExportRecorder, InMemoryStorageBackend],
    ) -> None:
        m = await make_material(db_session, alice, "summary", title='Evil"\r\nX: y <b>.pdf')
        created = await _call(
            client, alice, "POST", f"/study/materials/{m.id}/export", json={"format": "md"}
        )
        export_id = created.json()["data"]["id"]
        early = await _call(client, alice, "GET", f"/study/exports/{export_id}/download")
        assert early.status_code == 409 and early.json()["error"]["code"] == "EXPORT_NOT_READY"
        await run_export(_TestSessionLocal, exports[1], get_settings(), uuid.UUID(export_id))
        dl = await _call(client, alice, "GET", f"/study/exports/{export_id}/download")
        assert dl.headers["content-disposition"] == 'attachment; filename="study-export.md"'
        assert dl.headers["x-content-type-options"] == "nosniff"
        assert "no-store" in dl.headers["cache-control"]
        assert dl.headers["content-type"].startswith("text/markdown")
        # the storage key is neither in the status response nor derived from the title
        status = (await _call(client, alice, "GET", f"/study/exports/{export_id}")).text
        assert "users/" not in status and "storage" not in status

    async def test_expired_download_is_refused_and_sweeper_removes_file(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        alice: Actor,
        exports: tuple[ExportRecorder, InMemoryStorageBackend],
    ) -> None:
        m = await make_material(db_session, alice, "summary")
        export_id, _ = await export_file(client, alice, exports, m.id, "md")
        assert len(exports[1].keys()) == 1
        await db_session.execute(
            update(StudyExport)
            .where(StudyExport.id == uuid.UUID(export_id))
            .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        await db_session.commit()
        status = (await _call(client, alice, "GET", f"/study/exports/{export_id}")).json()["data"]
        assert status["status"] == "expired" and status["download_path"] is None
        dl = await _call(client, alice, "GET", f"/study/exports/{export_id}/download")
        assert dl.status_code == 410 and dl.json()["error"]["code"] == "EXPORT_EXPIRED"
        assert await expire_exports(_TestSessionLocal, exports[1]) == 1
        assert exports[1].keys() == []

    async def test_run_is_idempotent_and_render_failure_is_safe(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        alice: Actor,
        exports: tuple[ExportRecorder, InMemoryStorageBackend],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        m = await make_material(db_session, alice, "summary")
        export_id, _ = await export_file(client, alice, exports, m.id, "md")
        again = await run_export(
            _TestSessionLocal, exports[1], get_settings(), uuid.UUID(export_id)
        )
        assert again == "skipped"

        import app.study.export_runner as runner

        def boom(*_: Any) -> bytes:
            raise RuntimeError("SECRET-CONTENT")

        monkeypatch.setattr(runner, "render", boom)
        created = await _call(
            client, alice, "POST", f"/study/materials/{m.id}/export", json={"format": "md"}
        )
        new_id = created.json()["data"]["id"]
        assert (
            await run_export(_TestSessionLocal, exports[1], get_settings(), uuid.UUID(new_id))
            == "failed"
        )
        status = (await _call(client, alice, "GET", f"/study/exports/{new_id}")).json()["data"]
        assert status["status"] == "failed" and status["error_code"] == "EXPORT_RENDER_FAILED"
        assert "SECRET" not in json.dumps(status)

    async def test_unavailable_without_broker_and_rate_limit(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        alice: Actor,
        exports: tuple[ExportRecorder, InMemoryStorageBackend],
    ) -> None:
        m = await make_material(db_session, alice, "summary")
        exports[0].is_available = False
        resp = await _call(
            client, alice, "POST", f"/study/materials/{m.id}/export", json={"format": "md"}
        )
        assert resp.status_code == 503 and resp.json()["error"]["code"] == "EXPORT_UNAVAILABLE"
        exports[0].is_available = True
        limit = get_settings().study_exports_per_hour_per_user
        for _ in range(limit):
            ok = await _call(
                client, alice, "POST", f"/study/materials/{m.id}/export", json={"format": "md"}
            )
            assert ok.status_code == 202
        over = await _call(
            client, alice, "POST", f"/study/materials/{m.id}/export", json={"format": "md"}
        )
        assert over.status_code == 429

    async def test_deleting_material_queues_export_file_for_cleanup(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        alice: Actor,
        exports: tuple[ExportRecorder, InMemoryStorageBackend],
    ) -> None:
        m = await make_material(db_session, alice, "summary")
        export_id, _ = await export_file(client, alice, exports, m.id, "md")
        assert (await _call(client, alice, "DELETE", f"/study/materials/{m.id}")).status_code == 204
        db_session.expire_all()
        assert await db_session.get(StudyExport, uuid.UUID(export_id)) is None
        queued = (await db_session.execute(select(StorageCleanup))).scalars().all()
        assert [q.reason for q in queued] == ["study_material_deleted"]
        assert (await _call(client, alice, "GET", f"/study/exports/{export_id}")).status_code == 404


# pure rendering helpers ────────────────────────────────────────────────────


class TestRendering:
    @pytest.mark.parametrize(
        "payload",
        ["=1+1", "+1", "-1", "@SUM(A1)", "\tx", "\rx", "  =cmd|' /C calc'!A0", "\nSUM"],
    )
    def test_csv_injection_payloads_are_neutralised(self, payload: str) -> None:
        out = csv_safe(payload)
        assert out.startswith("'")
        assert not out.lstrip(" '").startswith(("=cmd", "@SUM")) or out.startswith("'")

    def test_csv_safe_keeps_normal_text(self) -> None:
        assert csv_safe("Energy = mc2") == "Energy = mc2"
        assert csv_safe(None) == ""
        assert csv_safe("a\x00b") == "ab"

    def test_glossary_csv_cells_are_all_safe(self) -> None:
        data = {
            "title": "G",
            "terms": [
                {
                    "term": "=EVIL()",
                    "definition": "@x",
                    "explanation": "-2",
                    "example": "+3",
                    "topic": "\tt",
                    "related_terms": ["=a", "b"],
                }
            ],
        }
        rows = list(
            csv.reader(io.StringIO(render_csv(ExportInput("glossary", "G", data, [], [])).decode()))
        )
        assert all(c.startswith("'") for c in rows[1][:5])

    def test_markdown_escapes_html_and_links(self) -> None:
        text = md_escape("<script>alert(1)</script> [x](javascript:alert(1)) `c` *b*")
        assert "<" not in text and "](" not in text.replace("\\]", "").replace("\\[", "")
        data = {
            "title": "<img src=x onerror=alert(1)>",
            "sections": [{"heading": "H", "body": "<b>x</b>"}],
        }
        out = render_markdown(ExportInput("summary", "<i>t</i>", data, [], [])).decode()
        assert "<" not in out

    def test_pdf_is_plain_text_even_for_hostile_and_non_latin_content(self) -> None:
        need_pdf()
        payload = {
            "title": "<script>alert(1)</script>",
            "sections": [
                {
                    "heading": "<b>Bold?</b> ‮ rtl \x00 中文",
                    "body": "<iframe src=//evil></iframe> " + "a" * 5000,
                    "bullets": ["[link](http://evil.example)"],
                }
            ],
        }
        pdf = render_pdf(ExportInput("summary", "<script>t</script>", payload, [], []))
        doc = pymupdf.open(stream=pdf, filetype="pdf")
        text = "".join(p.get_text() for p in doc)
        assert "<b>Bold?</b>" in text  # shown literally, never interpreted
        assert not any(page.get_links() for page in doc)
        assert doc.page_count >= 1

    def test_long_documents_paginate(self) -> None:
        need_pdf()
        payload = {
            "title": "Long",
            "sections": [{"heading": f"S{i}", "body": "word " * 300} for i in range(30)],
        }
        pdf = render_pdf(ExportInput("summary", "Long", payload, [], []))
        assert pymupdf.open(stream=pdf, filetype="pdf").page_count > 3


# account export and deletion ───────────────────────────────────────────────


class TestAccount:
    async def test_account_export_includes_study_data(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor
    ) -> None:
        await make_deck(db_session, alice, ["Front one?"])
        await make_quiz(db_session, alice)
        await _call(client, alice, "PUT", "/study/preferences", json={"language": "French"})
        resp = await _call(client, alice, "GET", "/users/me/export")
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        kinds = sorted(m["resource_type"] for m in data["study_materials"])
        assert kinds == ["flashcards", "quiz"]
        deck = next(m for m in data["study_materials"] if m["resource_type"] == "flashcards")
        assert (
            deck["flashcards"][0]["front"] == "Front one?"
            and deck["versions"][0]["version_number"] == 1
        )
        assert data["study_preferences"]["language"] == "French"
        assert "SECRET-EXPLANATION" not in resp.text and "correct_answers" not in resp.text

    async def test_account_export_does_not_include_other_users_study_data(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, bob: Actor
    ) -> None:
        await make_material(db_session, bob, "summary", title="Bob private")
        resp = await _call(client, alice, "GET", "/users/me/export")
        assert resp.json()["data"]["study_materials"] == []
        assert "Bob private" not in resp.text

    async def test_account_deletion_removes_study_data_and_queues_export_files(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        alice: Actor,
        exports: tuple[ExportRecorder, InMemoryStorageBackend],
    ) -> None:
        user_id = alice.user.id
        deck = await make_deck(db_session, alice, ["Front one?"])
        await make_quiz(db_session, alice)
        await export_file(client, alice, exports, deck.id, "csv")
        await _call(client, alice, "PUT", "/study/preferences", json={"language": "French"})
        resp = await _call(
            client,
            alice,
            "DELETE",
            "/users/me",
            json={"password": PASSWORD, "confirmation": "delete my account"},
        )
        assert resp.status_code == 200, resp.text
        db_session.expire_all()
        from app.models.flashcard import FlashcardSet
        from app.models.quiz import Quiz
        from app.models.study_material import StudyMaterialVersion
        from app.models.study_preferences import StudyGenerationPreferences

        for model in (
            StudyMaterial,
            StudyMaterialVersion,
            FlashcardSet,
            Quiz,
            StudyExport,
            StudyGenerationPreferences,
        ):
            rows = (
                await db_session.execute(select(model).where(model.user_id == user_id))  # type: ignore[attr-defined]
            ).first()
            assert rows is None, model.__name__
        queued = (await db_session.execute(select(StorageCleanup))).scalars().all()
        assert any("/exports/" in q.storage_key for q in queued)
