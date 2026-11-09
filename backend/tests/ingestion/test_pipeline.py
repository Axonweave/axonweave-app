"""End-to-end pipeline tests: real database, in-memory storage, fixtures generated in code."""

import asyncio
import hashlib
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import AppEnv, Settings, get_settings
from app.ingestion import pipeline
from app.ingestion.pipeline import PipelineDeps, run_job
from app.ingestion.version import PIPELINE_VERSION
from app.models.document import Document, DocumentVersion
from app.models.document_chunk import DocumentChunk
from app.models.document_processing_job import DocumentProcessingJob
from app.models.subject import Subject
from app.models.workspace import Workspace
from app.repositories.document_repository import DocumentRepository
from app.repositories.processing_job_repository import ProcessingJobRepository
from app.storage.base import StorageError
from app.storage.keys import build_original_key
from app.storage.memory_backend import InMemoryStorageBackend
from tests.conftest import _make_user, _TestSessionLocal
from tests.documents.helpers import make_pdf
from tests.ingestion import fixtures as fx

MARKER = "ZEBRA-PRIVATE-MARKER-4242"


async def _chunks_of(db: AsyncSession, document_id: uuid.UUID) -> list[DocumentChunk]:
    rows = await db.execute(
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index)
    )
    return list(rows.scalars().all())


class Env:
    def __init__(self, storage: InMemoryStorageBackend, user: Any, ws_id: Any, subject_id: Any):
        self.storage = storage
        self.user = user
        self.ws_id = ws_id
        self.subject_id = subject_id

    def deps(self, **changes: Any) -> PipelineDeps:
        settings: Settings = get_settings().model_copy(update=changes)
        return PipelineDeps(_TestSessionLocal, self.storage, settings)

    async def add(
        self, file_type: str, data: bytes, *, checksum: str | None = None, store: bool = True
    ) -> tuple[uuid.UUID, uuid.UUID]:
        """Create a document + version + queued job and put the bytes in storage."""
        document_id = uuid.uuid4()
        key = build_original_key(self.user.id, document_id, 1, file_type)
        mime = {"pdf": "application/pdf"}.get(file_type, "application/octet-stream")

        async def stream() -> AsyncIterator[bytes]:
            yield data

        if store:
            await self.storage.put(key, stream(), content_type=mime)
        async with _TestSessionLocal() as db:
            _, job_id = await DocumentRepository(db).create_with_version_and_job(
                document_id=document_id,
                user_id=self.user.id,
                workspace_id=self.ws_id,
                subject_id=self.subject_id,
                folder_id=None,
                chapter_id=None,
                display_name=f"d.{file_type}",
                original_filename=f"d.{file_type}",
                file_type=file_type,
                mime_type=mime,
                file_size=len(data),
                checksum=checksum or hashlib.sha256(data).hexdigest(),
                storage_key=key,
                pipeline_version=PIPELINE_VERSION,
            )
            await db.commit()
        return document_id, job_id

    async def snapshot(self, document_id: uuid.UUID) -> dict[str, Any]:
        async with _TestSessionLocal() as db:
            doc = (
                await db.execute(select(Document).where(Document.id == document_id))
            ).scalar_one()
            version = (
                await db.execute(
                    select(DocumentVersion).where(DocumentVersion.document_id == document_id)
                )
            ).scalar_one()
            jobs = (
                (
                    await db.execute(
                        select(DocumentProcessingJob)
                        .where(DocumentProcessingJob.document_id == document_id)
                        .order_by(DocumentProcessingJob.created_at)
                    )
                )
                .scalars()
                .all()
            )
            chunks = await _chunks_of(db, document_id)
        return {"doc": doc, "version": version, "jobs": list(jobs), "chunks": chunks}


@pytest.fixture
async def env(db_session: AsyncSession) -> Env:
    user = await _make_user(db_session, email="pipeline@example.com")
    ws = Workspace(user_id=user.id, name="WS", workspace_type="personal_learning", is_default=False)
    db_session.add(ws)
    await db_session.flush()
    subject = Subject(workspace_id=ws.id, name="Subj")
    db_session.add(subject)
    await db_session.flush()
    await db_session.commit()
    return Env(InMemoryStorageBackend(AppEnv.testing), user, ws.id, subject.id)


class TestSuccess:
    async def test_text_file_completes_with_chunks_and_metadata(self, env: Env):
        text = "\n\n".join(fx.paragraph(i) for i in range(12)).encode()
        document_id, job_id = await env.add("txt", text)
        assert await run_job(env.deps(), job_id) == pipeline.SUCCEEDED

        snap = await env.snapshot(document_id)
        doc, version, job = snap["doc"], snap["version"], snap["jobs"][0]
        assert doc.processing_status == "completed" and doc.active_version == 1
        assert version.processing_status == "completed"
        assert version.extraction_method == "text" and version.ocr_used is False
        assert version.word_count and version.pipeline_version == PIPELINE_VERSION
        assert job.status == "succeeded" and job.stage == "done" and job.error_code is None
        chunks = snap["chunks"]
        assert len(chunks) >= 2
        assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
        assert all(c.user_id == env.user.id and c.document_id == document_id for c in chunks)
        assert all(c.workspace_id == env.ws_id and c.subject_id == env.subject_id for c in chunks)
        assert all(c.embedding is None for c in chunks)  # embeddings arrive in M4
        assert all(c.token_count > 0 and c.char_count == len(c.content) for c in chunks)

    async def test_markdown_headings_become_section_headings(self, env: Env):
        body = "\n\n".join(fx.paragraph(i) for i in range(6))
        md = f"# Biology\n\n{body}\n\n## Cells\n\n{fx.paragraph(1)}\n".encode()
        document_id, job_id = await env.add("md", md)
        await run_job(env.deps(), job_id)
        headings = {c.section_heading for c in (await env.snapshot(document_id))["chunks"]}
        assert "Cells" in headings

    async def test_pdf_pages_provenance_and_bboxes(self, env: Env):
        data = fx.make_text_pdf(
            [
                [("Plant Biology", 24), (fx.paragraph(0), 11)],
                [("Light Reactions", 20), (fx.paragraph(1), 11)],
                [(fx.paragraph(2), 11)],
            ]
        )
        document_id, job_id = await env.add("pdf", data)
        assert await run_job(env.deps(), job_id) == pipeline.SUCCEEDED
        snap = await env.snapshot(document_id)
        assert snap["version"].page_count == 3 and snap["version"].extraction_method == "pymupdf"
        pages = {c.page_number for c in snap["chunks"]}
        assert pages == {1, 2, 3}
        assert all(c.bboxes for c in snap["chunks"])
        assert any(c.section_heading == "Light Reactions" for c in snap["chunks"])

    async def test_pptx_slides_have_slide_numbers_not_pages(self, env: Env):
        data = fx.make_pptx_file(
            [("Cells", "Nucleus", "speaker note here"), ("Energy", "Mitochondria", "")]
        )
        document_id, job_id = await env.add("pptx", data)
        assert await run_job(env.deps(), job_id) == pipeline.SUCCEEDED
        snap = await env.snapshot(document_id)
        assert snap["version"].slide_count == 2
        assert {c.slide_number for c in snap["chunks"]} == {1, 2}
        assert all(c.page_number is None for c in snap["chunks"])

    async def test_docx_completes(self, env: Env):
        data = fx.make_docx_file(
            "Genetics", [fx.paragraph(0)], [["Allele", "Trait"], ["A", "Tall"]]
        )
        document_id, job_id = await env.add("docx", data)
        assert await run_job(env.deps(), job_id) == pipeline.SUCCEEDED
        snap = await env.snapshot(document_id)
        assert any("Allele | Trait" in c.content for c in snap["chunks"])

    async def test_scanned_pdf_is_ocrd_with_confidence_and_warning(self, env: Env):
        fx.need_tesseract()
        document_id, job_id = await env.add("pdf", fx.make_scanned_pdf("Mitochondria produce ATP"))
        assert await run_job(env.deps(), job_id) == pipeline.SUCCEEDED
        snap = await env.snapshot(document_id)
        version = snap["version"]
        assert version.ocr_used is True and version.ocr_mean_confidence
        assert "OCR_USED" in version.warnings
        assert all(c.extraction_confidence is not None for c in snap["chunks"])

    async def test_image_document_is_ocrd(self, env: Env):
        fx.need_tesseract()
        document_id, job_id = await env.add("png", fx.text_image_png("Chloroplast"))
        assert await run_job(env.deps(), job_id) == pipeline.SUCCEEDED
        assert "chloroplast" in (await env.snapshot(document_id))["chunks"][0].content.lower()

    async def test_extraction_limit_adds_a_warning(self, env: Env):
        document_id, job_id = await env.add("txt", fx.paragraph(0).encode() * 20)
        await run_job(env.deps(doc_max_extracted_chars=300), job_id)
        assert "TEXT_TRUNCATED" in (await env.snapshot(document_id))["version"].warnings


class TestFailures:
    @pytest.mark.parametrize(
        ("file_type", "data_factory", "code"),
        [
            ("pdf", lambda: fx.make_encrypted_pdf(), "FILE_ENCRYPTED"),
            ("pdf", lambda: b"%PDF-1.4\nnot really a pdf at all, just text", "FILE_CORRUPT"),
            ("txt", lambda: b"   \n\n  ", "NO_TEXT_FOUND"),
        ],
    )
    async def test_unprocessable_documents_fail_with_a_safe_code(
        self, env: Env, file_type, data_factory, code
    ):
        document_id, job_id = await env.add(file_type, data_factory())
        assert await run_job(env.deps(), job_id) == pipeline.FAILED
        snap = await env.snapshot(document_id)
        assert snap["jobs"][0].status == "failed" and snap["jobs"][0].error_code == code
        assert snap["version"].processing_status == "failed"
        assert snap["doc"].processing_status == "failed" and snap["doc"].active_version is None
        assert snap["chunks"] == []

    async def test_page_limit_fails_the_job(self, env: Env):
        data = fx.make_text_pdf([[(fx.paragraph(i), 11)] for i in range(3)])
        document_id, job_id = await env.add("pdf", data)
        await run_job(env.deps(doc_max_pages=2), job_id)
        assert (await env.snapshot(document_id))["jobs"][0].error_code == "TOO_MANY_PAGES"

    async def test_blank_pdf_without_ocr(self, env: Env):
        document_id, job_id = await env.add("pdf", fx.make_blank_pdf())
        await run_job(env.deps(doc_ocr_enabled=False), job_id)
        assert (await env.snapshot(document_id))["jobs"][0].error_code == "NO_TEXT_FOUND"

    async def test_tampered_object_is_rejected_by_checksum(self, env: Env):
        document_id, job_id = await env.add("txt", b"original text " * 10, checksum="0" * 64)
        assert await run_job(env.deps(), job_id) == pipeline.FAILED
        assert (await env.snapshot(document_id))["jobs"][0].error_code == "FILE_CHECKSUM_MISMATCH"

    async def test_content_that_no_longer_matches_its_type_is_rejected(self, env: Env):
        # Stored as "txt" but the bytes are a PDF: the worker re-validates before parsing.
        document_id, job_id = await env.add("txt", make_pdf())
        assert await run_job(env.deps(), job_id) == pipeline.FAILED
        assert (await env.snapshot(document_id))["jobs"][0].error_code == "FILE_CONTENT_MISMATCH"

    async def test_missing_object_fails_permanently(self, env: Env):
        document_id, job_id = await env.add("txt", b"hello there world", store=False)
        assert await run_job(env.deps(), job_id) == pipeline.FAILED
        assert (await env.snapshot(document_id))["jobs"][0].error_code == "STORAGE_OBJECT_NOT_FOUND"

    async def test_timeout_and_memory_errors_map_to_safe_codes(
        self, env: Env, monkeypatch: pytest.MonkeyPatch
    ):
        from celery.exceptions import SoftTimeLimitExceeded

        for exc, code in (
            (SoftTimeLimitExceeded(), "TASK_TIMEOUT"),
            (MemoryError(), "MEMORY_LIMIT"),
        ):
            document_id, job_id = await env.add("txt", fx.paragraph(0).encode())

            def boom(*_: Any, _exc: BaseException = exc, **__: Any) -> None:
                raise _exc

            monkeypatch.setattr(pipeline, "extract", boom)
            assert await run_job(env.deps(), job_id) == pipeline.FAILED
            assert (await env.snapshot(document_id))["jobs"][0].error_code == code

    async def test_unexpected_error_is_internal_and_leaks_nothing(
        self, env: Env, monkeypatch: pytest.MonkeyPatch
    ):
        document_id, job_id = await env.add("txt", fx.paragraph(0).encode())

        def boom(*_: Any, **__: Any) -> None:
            raise RuntimeError(f"secret detail {MARKER} /etc/passwd SELECT *")

        monkeypatch.setattr(pipeline, "extract", boom)
        assert await run_job(env.deps(), job_id) == pipeline.FAILED
        job = (await env.snapshot(document_id))["jobs"][0]
        assert job.error_code == "INTERNAL"
        assert MARKER not in repr(job.__dict__)

    async def test_transient_storage_error_requeues_then_fails_after_the_limit(
        self, env: Env, monkeypatch: pytest.MonkeyPatch
    ):
        document_id, job_id = await env.add("txt", fx.paragraph(0).encode())

        def down(key: str, chunk_size: int = 0) -> AsyncIterator[bytes]:
            raise StorageError("down")

        monkeypatch.setattr(env.storage, "open", down)
        deps = env.deps(celery_max_retries=2)
        assert await run_job(deps, job_id) == pipeline.RETRY
        snap = await env.snapshot(document_id)
        assert snap["jobs"][0].status == "queued" and snap["jobs"][0].retry_count == 1
        assert snap["doc"].processing_status == "queued"
        assert await run_job(deps, job_id) == pipeline.RETRY
        assert await run_job(deps, job_id) == pipeline.FAILED
        job = (await env.snapshot(document_id))["jobs"][0]
        assert job.status == "failed" and job.error_code == "STORAGE_ERROR"

    async def test_failed_reprocess_does_not_leave_a_searchable_version(self, env: Env):
        document_id, job_id = await env.add("txt", fx.paragraph(0).encode())
        await run_job(env.deps(), job_id)
        async with _TestSessionLocal() as db:
            version = (await db.execute(select(DocumentVersion))).scalar_one()
            version.checksum = "f" * 64  # simulate the stored object changing
            await db.commit()
            job = await ProcessingJobRepository(db).create_queued(
                user_id=env.user.id,
                document_id=document_id,
                version_id=version.id,
                pipeline=PIPELINE_VERSION,
            )
            await db.commit()
        await run_job(env.deps(), job.id)
        snap = await env.snapshot(document_id)
        assert snap["version"].processing_status == "failed"


class TestIdempotencyAndConcurrency:
    async def test_rerunning_a_finished_job_is_a_no_op(self, env: Env):
        document_id, job_id = await env.add("txt", fx.paragraph(0).encode() * 5)
        assert await run_job(env.deps(), job_id) == pipeline.SUCCEEDED
        before = [c.id for c in (await env.snapshot(document_id))["chunks"]]
        assert await run_job(env.deps(), job_id) == pipeline.SKIPPED  # redelivered message
        assert [c.id for c in (await env.snapshot(document_id))["chunks"]] == before

    async def test_duplicate_deliveries_at_the_same_time_run_once(self, env: Env):
        document_id, job_id = await env.add(
            "txt", "\n\n".join(fx.paragraph(i) for i in range(8)).encode()
        )
        results = await asyncio.gather(
            run_job(env.deps(), job_id), run_job(env.deps(), job_id), run_job(env.deps(), job_id)
        )
        assert sorted(results) == [pipeline.SKIPPED, pipeline.SKIPPED, pipeline.SUCCEEDED]
        chunks = (await env.snapshot(document_id))["chunks"]
        assert [c.chunk_index for c in chunks] == list(range(len(chunks)))  # no duplicates

    async def test_two_jobs_for_one_version_never_run_together(self, env: Env):
        document_id, first = await env.add(
            "txt", "\n\n".join(fx.paragraph(i) for i in range(8)).encode()
        )
        async with _TestSessionLocal() as db:
            version = (await db.execute(select(DocumentVersion))).scalar_one()
            second = await ProcessingJobRepository(db).create_queued(
                user_id=env.user.id,
                document_id=document_id,
                version_id=version.id,
                pipeline=PIPELINE_VERSION,
            )
            await db.commit()
        results = await asyncio.gather(run_job(env.deps(), first), run_job(env.deps(), second.id))
        assert pipeline.SUCCEEDED in results
        chunks = (await env.snapshot(document_id))["chunks"]
        assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
        async with _TestSessionLocal() as db:
            running = await db.execute(
                select(func.count(DocumentProcessingJob.id)).where(
                    DocumentProcessingJob.status == "running"
                )
            )
            assert running.scalar_one() == 0

    async def test_reprocessing_rebuilds_chunks_without_duplicates(self, env: Env):
        text = "\n\n".join(fx.paragraph(i) for i in range(12)).encode()
        document_id, first = await env.add("txt", text)
        await run_job(env.deps(), first)
        before = await env.snapshot(document_id)
        async with _TestSessionLocal() as db:
            second = await ProcessingJobRepository(db).create_queued(
                user_id=env.user.id,
                document_id=document_id,
                version_id=before["version"].id,
                pipeline=PIPELINE_VERSION,
            )
            await db.commit()
        assert await run_job(env.deps(), second.id) == pipeline.SUCCEEDED
        after = await env.snapshot(document_id)
        assert [c.content for c in after["chunks"]] == [c.content for c in before["chunks"]]
        assert {c.id for c in after["chunks"]}.isdisjoint({c.id for c in before["chunks"]})
        assert len(after["jobs"]) == 2 and all(j.status == "succeeded" for j in after["jobs"])

    async def test_cancel_flag_stops_the_job_between_stages(self, env: Env):
        document_id, job_id = await env.add("txt", fx.paragraph(0).encode() * 5)
        async with _TestSessionLocal() as db:
            await ProcessingJobRepository(db).request_cancel(job_id)
            await db.commit()
        assert await run_job(env.deps(), job_id) == pipeline.CANCELLED
        snap = await env.snapshot(document_id)
        assert snap["jobs"][0].status == "cancelled" and snap["chunks"] == []
        assert snap["version"].processing_status == "cancelled"
        assert snap["doc"].processing_status == "cancelled"

    async def test_deleted_document_mid_flight_is_not_resurrected(self, env: Env):
        document_id, job_id = await env.add("txt", fx.paragraph(0).encode() * 5)
        async with _TestSessionLocal() as db:
            await db.delete((await db.execute(select(Document))).scalar_one())
            await db.commit()
        assert await run_job(env.deps(), job_id) == pipeline.SKIPPED
        async with _TestSessionLocal() as db:
            assert (await db.execute(select(func.count(DocumentChunk.id)))).scalar_one() == 0

    async def test_stale_queued_jobs_are_found_for_redispatch(self, env: Env):
        from datetime import UTC, datetime, timedelta

        _, job_id = await env.add("txt", b"queued but never delivered")
        async with _TestSessionLocal() as db:
            repo = ProcessingJobRepository(db)
            now = datetime.now(UTC)
            assert await repo.queued_older_than(now - timedelta(seconds=90), 10) == []
            assert await repo.queued_older_than(now + timedelta(seconds=5), 10) == [job_id]
            await repo.touch(job_id, now + timedelta(seconds=10))
            await db.commit()
            assert await repo.queued_older_than(now + timedelta(seconds=5), 10) == []


class TestPrivacy:
    async def test_document_text_never_reaches_the_logs(
        self, env: Env, capsys: pytest.CaptureFixture[str]
    ):
        body = f"{MARKER} " + fx.paragraph(0)
        _, ok_job = await env.add("txt", body.encode())
        _, bad_job = await env.add("pdf", b"%PDF-1.4 " + MARKER.encode())
        await run_job(env.deps(), ok_job)
        await run_job(env.deps(), bad_job)
        captured = capsys.readouterr()
        assert MARKER not in captured.out and MARKER not in captured.err
        assert "document_job_succeeded" in captured.out + captured.err
