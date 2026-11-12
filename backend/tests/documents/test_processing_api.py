# ruff: noqa: F811
"""Phase 3 M3: processing control and extracted-content endpoints (spec 19.2)."""

import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import get_settings
from app.ingestion import pipeline
from app.ingestion.pipeline import PipelineDeps, run_job
from app.models.document_processing_job import DocumentProcessingJob
from app.repositories.processing_job_repository import ProcessingJobRepository
from app.storage.memory_backend import InMemoryStorageBackend
from tests.conftest import _TestSessionLocal
from tests.documents.conftest import FakeDispatcher
from tests.documents.helpers import make_pdf
from tests.documents.test_documents_api import (  # noqa: F401 (fixtures)
    Actor,
    alice,
    bob,
    call,
    storage,
    upload,
    upload_one,
)
from tests.ingestion import fixtures as fx


def text_file(paragraphs: int = 12) -> bytes:
    return "\n\n".join(fx.paragraph(i) for i in range(paragraphs)).encode()


async def process(storage: InMemoryStorageBackend, job_id: uuid.UUID, **changes: Any) -> str:
    settings = get_settings().model_copy(update=changes)
    return await run_job(PipelineDeps(_TestSessionLocal, storage, settings), job_id)


async def only_job(document_id: str) -> uuid.UUID:
    async with _TestSessionLocal() as db:
        rows = await db.execute(
            select(DocumentProcessingJob.id)
            .where(DocumentProcessingJob.document_id == uuid.UUID(document_id))
            .order_by(DocumentProcessingJob.created_at.desc())
        )
        return rows.scalars().first()  # type: ignore[return-value]


class TestUploadDispatch:
    async def test_upload_hands_the_job_to_the_dispatcher(
        self, client: AsyncClient, alice: Actor, storage, dispatcher: FakeDispatcher
    ):
        doc = await upload_one(client, alice, "a.txt", text_file(3))
        assert dispatcher.sent == [await only_job(doc["id"])]

    async def test_upload_is_refused_when_nothing_could_process_it(
        self, client: AsyncClient, alice: Actor, storage, dispatcher: FakeDispatcher
    ):
        dispatcher.is_available = False
        resp = await upload(client, alice, [("a.pdf", make_pdf())])
        assert resp.status_code == 503
        assert resp.json()["error"]["code"] == "PROCESSING_UNAVAILABLE"
        assert storage.keys() == []
        # Reading and managing existing documents does not need the broker.
        assert (await call(client, alice, "GET", "/documents")).status_code == 200


class TestProcessingDetails:
    async def test_full_flow_status_details_pages_and_content(
        self, client: AsyncClient, alice: Actor, storage: InMemoryStorageBackend
    ):
        data = fx.make_text_pdf(
            [
                [("Plant Biology", 24), (fx.paragraph(0), 11)],
                [("Light Reactions", 20), (fx.paragraph(1), 11)],
            ]
        )
        doc = await upload_one(client, alice, "plants.pdf", data)
        url = f"/documents/{doc['id']}"
        # Not processed yet: the content endpoints say so instead of returning nothing.
        assert (await call(client, alice, "GET", f"{url}/pages")).status_code == 409
        assert (await call(client, alice, "GET", f"{url}/content")).json()["error"]["code"] == (
            "DOCUMENT_NOT_READY"
        )
        queued = (await call(client, alice, "GET", f"{url}/processing")).json()["data"]
        assert queued["processing_status"] == "queued" and queued["chunk_count"] == 0

        assert await process(storage, await only_job(doc["id"])) == pipeline.SUCCEEDED

        status = (await call(client, alice, "GET", f"{url}/status")).json()["data"]
        assert status["processing_status"] == "completed" and status["job_status"] == "succeeded"
        details = (await call(client, alice, "GET", f"{url}/processing")).json()["data"]
        assert details["page_count"] == 2 and details["chunk_count"] >= 2
        assert details["extraction_method"] == "pymupdf" and details["ocr_used"] is False
        assert details["jobs"][0]["status"] == "succeeded"
        assert "storage_key" not in str(details)

        pages = (await call(client, alice, "GET", f"{url}/pages")).json()["data"]
        assert [(p["number"], p["kind"]) for p in pages] == [(1, "page"), (2, "page")]

        content = (await call(client, alice, "GET", f"{url}/content?page=2")).json()
        assert content["total"] >= 1
        assert all(c["page_number"] == 2 for c in content["data"])
        assert any("Calvin" in c["text"] or "Chlorophyll" in c["text"] for c in content["data"])
        paged = (await call(client, alice, "GET", f"{url}/content?limit=1&offset=1")).json()
        assert len(paged["data"]) == 1 and paged["total"] >= 2
        doc_after = (await call(client, alice, "GET", url)).json()["data"]
        assert doc_after["processing_status"] == "completed" and doc_after["active_version"] == 1

    async def test_slide_content_filter(
        self, client: AsyncClient, alice: Actor, storage: InMemoryStorageBackend
    ):
        data = fx.make_pptx_file([("Cells", "Nucleus", "note"), ("Energy", "Mitochondria", "")])
        doc = await upload_one(client, alice, "s.pptx", data)
        await process(storage, await only_job(doc["id"]))
        url = f"/documents/{doc['id']}"
        pages = (await call(client, alice, "GET", f"{url}/pages")).json()["data"]
        assert [(p["number"], p["kind"]) for p in pages] == [(1, "slide"), (2, "slide")]
        content = (await call(client, alice, "GET", f"{url}/content?slide=2")).json()["data"]
        assert content and all(c["slide_number"] == 2 for c in content)

    @pytest.mark.parametrize("query", ["page=0", "slide=-1", "limit=0", "limit=51", "offset=-1"])
    async def test_content_validates_input(self, client: AsyncClient, alice: Actor, storage, query):
        doc = await upload_one(client, alice, "a.txt", text_file(3))
        resp = await call(client, alice, "GET", f"/documents/{doc['id']}/content?{query}")
        assert resp.status_code == 422

    async def test_failed_processing_reports_a_safe_code(
        self, client: AsyncClient, alice: Actor, storage: InMemoryStorageBackend
    ):
        pytest.importorskip("fitz")  # PyMuPDF is a worker-image dependency
        doc = await upload_one(client, alice, "a.pdf", make_pdf(b"not parseable"))
        assert await process(storage, await only_job(doc["id"])) == pipeline.FAILED
        status = (await call(client, alice, "GET", f"/documents/{doc['id']}/status")).json()["data"]
        assert status["processing_status"] == "failed" and status["error_code"] == "FILE_CORRUPT"
        listing = (await call(client, alice, "GET", "/documents?status=failed")).json()
        assert listing["total"] == 1


class TestRetryReprocessCancel:
    async def test_retry_only_after_failure_and_dispatches_a_new_job(
        self, client: AsyncClient, alice: Actor, storage, dispatcher: FakeDispatcher
    ):
        doc = await upload_one(client, alice, "a.pdf", make_pdf(b"not parseable"))
        url = f"/documents/{doc['id']}"
        busy = await call(client, alice, "POST", f"{url}/retry")  # still queued
        assert busy.status_code == 409
        assert busy.json()["error"]["code"] == "PROCESSING_IN_PROGRESS"

        await process(storage, await only_job(doc["id"]))
        before = len(dispatcher.sent)
        resp = await call(client, alice, "POST", f"{url}/retry")
        assert resp.status_code == 200 and resp.json()["data"]["processing_status"] == "queued"
        assert len(dispatcher.sent) == before + 1
        assert dispatcher.sent[-1] == await only_job(doc["id"])
        async with _TestSessionLocal() as db:
            jobs = (await db.execute(select(DocumentProcessingJob))).scalars().all()
            assert sorted(j.status for j in jobs) == ["failed", "queued"]

    async def test_retry_is_not_for_completed_documents_but_reprocess_is(
        self, client: AsyncClient, alice: Actor, storage, dispatcher: FakeDispatcher
    ):
        doc = await upload_one(client, alice, "a.txt", text_file())
        url = f"/documents/{doc['id']}"
        await process(storage, await only_job(doc["id"]))
        denied = await call(client, alice, "POST", f"{url}/retry")
        assert denied.status_code == 409 and denied.json()["error"]["code"] == "NOT_RETRYABLE"

        resp = await call(client, alice, "POST", f"{url}/reprocess")
        assert resp.status_code == 200 and resp.json()["data"]["processing_status"] == "queued"
        assert await process(storage, await only_job(doc["id"])) == pipeline.SUCCEEDED
        details = (await call(client, alice, "GET", f"{url}/processing")).json()["data"]
        assert [j["status"] for j in details["jobs"]] == ["succeeded", "succeeded"]
        chunks = (await call(client, alice, "GET", f"{url}/content?limit=50")).json()
        assert [c["chunk_index"] for c in chunks["data"]] == list(range(chunks["total"]))

    async def test_processing_control_needs_a_broker(
        self, client: AsyncClient, alice: Actor, storage, dispatcher: FakeDispatcher
    ):
        doc = await upload_one(client, alice, "a.pdf", make_pdf(b"not parseable"))
        await process(storage, await only_job(doc["id"]))
        dispatcher.is_available = False
        for action in ("retry", "reprocess"):
            resp = await call(client, alice, "POST", f"/documents/{doc['id']}/{action}")
            assert resp.status_code == 503
            assert resp.json()["error"]["code"] == "PROCESSING_UNAVAILABLE"

    async def test_cancel_a_queued_job(self, client: AsyncClient, alice: Actor, storage):
        doc = await upload_one(client, alice, "a.txt", text_file(3))
        url = f"/documents/{doc['id']}"
        resp = await call(client, alice, "POST", f"{url}/cancel")
        assert resp.status_code == 200 and resp.json()["data"]["processing_status"] == "cancelled"
        again = await call(client, alice, "POST", f"{url}/cancel")
        assert again.status_code == 409 and again.json()["error"]["code"] == "NOTHING_TO_CANCEL"
        # A cancelled document can be retried.
        assert (await call(client, alice, "POST", f"{url}/retry")).status_code == 200

    async def test_cancel_a_running_job_sets_the_flag(
        self, client: AsyncClient, alice: Actor, storage
    ):
        from datetime import UTC, datetime

        doc = await upload_one(client, alice, "a.txt", text_file(3))
        job_id = await only_job(doc["id"])
        async with _TestSessionLocal() as db:
            await ProcessingJobRepository(db).claim(job_id, datetime.now(UTC), None)
            await db.commit()
        resp = await call(client, alice, "POST", f"/documents/{doc['id']}/cancel")
        assert resp.status_code == 200
        async with _TestSessionLocal() as db:
            assert await ProcessingJobRepository(db).cancel_requested(job_id) is True


class TestAccessControl:
    ROUTES = [
        ("GET", "/documents/{id}/processing"),
        ("GET", "/documents/{id}/pages"),
        ("GET", "/documents/{id}/content"),
        ("POST", "/documents/{id}/retry"),
        ("POST", "/documents/{id}/reprocess"),
        ("POST", "/documents/{id}/cancel"),
    ]

    @pytest.mark.parametrize(("method", "path"), ROUTES)
    async def test_other_users_document_is_404(
        self, client: AsyncClient, alice: Actor, bob: Actor, storage, method, path
    ):
        doc = await upload_one(client, alice, "a.txt", text_file(3))
        await process(storage, await only_job(doc["id"]))
        resp = await call(client, bob, method, path.format(id=doc["id"]))
        assert resp.status_code == 404 and resp.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"
        unknown = await call(client, bob, method, path.format(id=uuid.uuid4()))
        assert unknown.json() == resp.json()

    async def test_extracted_text_is_never_served_to_another_user(
        self, client: AsyncClient, alice: Actor, bob: Actor, storage
    ):
        doc = await upload_one(client, alice, "a.txt", text_file(3))
        await process(storage, await only_job(doc["id"]))
        for url in (f"/documents/{doc['id']}/content", f"/documents/{doc['id']}/pages"):
            resp = await call(client, bob, "GET", url)
            assert resp.status_code == 404 and "Calvin" not in resp.text

    async def test_api_process_does_not_load_parser_libraries(self):
        import subprocess
        import sys

        code = (
            "import sys, app.main\n"
            "bad = [m for m in ('pymupdf', 'fitz', 'pptx', 'docx', 'pytesseract', 'PIL')"
            " if m in sys.modules]\n"
            "print(','.join(bad))"
        )
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        assert out.returncode == 0, out.stderr[-500:]
        assert out.stdout.strip() == ""
