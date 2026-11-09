"""The document processing pipeline (spec 6, D-68, D-70).

One job processes one document version: validate -> extract (OCR where a page has no text) ->
normalise -> chunk -> [embed: M4] -> write. It runs only in the Celery worker.

Properties:
- Duplicate or redelivered tasks are harmless: `claim` moves queued -> running in one statement, and
  a partial unique index allows one running job per version.
- The write stage deletes and rebuilds the version's chunks in ONE transaction, so a retry never
  leaves duplicate or half-written chunks.
- A cancel flag in the database is checked between stages.
- Only safe codes reach the database and the logs: never document text, file names, paths or SQL.
"""

from __future__ import annotations

import asyncio
import tempfile
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import BinaryIO, Protocol, cast

import structlog
from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.ingestion import errors
from app.ingestion.chunker import ChunkDraft, ChunkSettings, chunk_blocks
from app.ingestion.extractors import extract
from app.ingestion.extractors.base import (
    FILE_CHECKSUM_MISMATCH,
    Extraction,
    ExtractionError,
    ExtractionLimits,
)
from app.ingestion.normalise import normalise_blocks, word_count
from app.ingestion.version import PIPELINE_VERSION
from app.modules.documents.validation import Limits, UploadRejected, detect_and_validate
from app.repositories.document_chunk_repository import DocumentChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.processing_job_repository import ProcessingJobRepository
from app.storage.base import StorageBackend, StorageError, StorageNotFoundError

logger = structlog.get_logger(__name__)

SUCCEEDED, FAILED, CANCELLED, SKIPPED, RETRY = (
    "succeeded",
    "failed",
    "cancelled",
    "skipped",
    "retry",
)
_CHUNK = 64 * 1024


class Embedder(Protocol):
    """Hook for M4. Given chunk drafts, return one vector each (and the model that made them)."""

    async def embed(self, drafts: list[ChunkDraft]) -> tuple[list[list[float]], str]: ...


class JobCancelledError(Exception):
    pass


@dataclass
class PipelineDeps:
    session_factory: async_sessionmaker[AsyncSession]
    storage: StorageBackend
    settings: Settings
    embedder: Embedder | None = None


def _now() -> datetime:
    return datetime.now(UTC)


def _limits(settings: Settings) -> ExtractionLimits:
    return ExtractionLimits(
        max_pages=settings.doc_max_pages,
        max_chars=settings.doc_max_extracted_chars,
        ocr_enabled=settings.doc_ocr_enabled,
        ocr_dpi=settings.doc_ocr_dpi,
        ocr_languages=settings.doc_ocr_languages,
        image_max_pixels=settings.doc_image_max_pixels,
        ocr_timeout_seconds=settings.doc_ocr_timeout_seconds,
    )


def _upload_limits(settings: Settings) -> Limits:
    return Limits(
        max_file_bytes=settings.doc_max_file_bytes,
        zip_max_entries=settings.doc_zip_max_entries,
        zip_max_uncompressed_bytes=settings.doc_zip_max_uncompressed_bytes,
        zip_max_ratio=settings.doc_zip_max_ratio,
        image_max_pixels=settings.doc_image_max_pixels,
    )


async def _read_object(
    storage: StorageBackend, key: str, max_bytes: int
) -> tempfile.SpooledTemporaryFile[bytes]:
    """Stream the original into a bounded temp file (in /scratch via TMPDIR, removed on close)."""
    spool: tempfile.SpooledTemporaryFile[bytes] = tempfile.SpooledTemporaryFile(
        max_size=1024 * 1024
    )
    total = 0
    try:
        async for chunk in storage.open(key):
            total += len(chunk)
            if total > max_bytes:
                raise UploadRejected("FILE_TOO_LARGE", "The file is too large.")
            spool.write(chunk)
    except BaseException:
        spool.close()
        raise
    spool.seek(0)
    return spool


async def _set_status(
    deps: PipelineDeps,
    job_id: uuid.UUID,
    user_id: uuid.UUID,
    version_id: uuid.UUID,
    status: str,
    stage: str,
) -> None:
    """Short transaction so progress and heartbeat are visible while the job runs."""
    async with deps.session_factory() as db:
        docs = DocumentRepository(db)
        version = await docs.get_version_by_id(version_id=version_id, user_id=user_id)
        if version is None:
            return
        doc = await docs.get_owned(document_id=version.document_id, user_id=user_id)
        if doc is None:
            return
        await docs.set_version_status(doc=doc, version=version, status=status)
        await ProcessingJobRepository(db).set_stage(job_id, stage, _now())
        await db.commit()


async def _check_cancel(deps: PipelineDeps, job_id: uuid.UUID) -> None:
    async with deps.session_factory() as db:
        if await ProcessingJobRepository(db).cancel_requested(job_id):
            raise JobCancelledError


async def _finish_failed(
    deps: PipelineDeps,
    job_id: uuid.UUID,
    user_id: uuid.UUID,
    version_id: uuid.UUID,
    code: str,
    *,
    status: str = "failed",
) -> None:
    async with deps.session_factory() as db:
        docs = DocumentRepository(db)
        version = await docs.get_version_by_id(version_id=version_id, user_id=user_id)
        if version is not None:
            doc = await docs.get_owned(document_id=version.document_id, user_id=user_id)
            if doc is not None:
                await docs.set_version_status(doc=doc, version=version, status=status)
        await ProcessingJobRepository(db).finish(
            job_id,
            "cancelled" if status == "cancelled" else "failed",
            None if status == "cancelled" else code,
            _now(),
        )
        await db.commit()


def _build_rows(drafts: list[ChunkDraft], ocr_confidence: float | None) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index, d in enumerate(drafts):
        rows.append(
            {
                "chunk_index": index,
                "content": d.text,
                "page_number": d.page,
                "slide_number": d.slide,
                "section_heading": d.heading,
                "bboxes": d.bboxes,
                "token_count": d.token_count,
                "char_count": d.char_count,
                "extraction_confidence": (
                    round(ocr_confidence / 100, 3)
                    if d.from_ocr and ocr_confidence is not None
                    else None
                ),
            }
        )
    return rows


async def _write(
    deps: PipelineDeps,
    *,
    job_id: uuid.UUID,
    user_id: uuid.UUID,
    version_id: uuid.UUID,
    extraction: Extraction,
    drafts: list[ChunkDraft],
    words: int,
) -> int:
    """The only stage that changes chunks: one transaction, delete-and-rebuild (D-68)."""
    async with deps.session_factory() as db:
        docs = DocumentRepository(db)
        version = await docs.get_version_by_id(version_id=version_id, user_id=user_id)
        doc = (
            await docs.get_owned(document_id=version.document_id, user_id=user_id)
            if version is not None
            else None
        )
        if version is None or doc is None:
            raise JobCancelledError  # deleted while running: nothing to write
        await DocumentChunkRepository(db).replace_for_version(
            user_id=user_id,
            document_id=doc.id,
            version_id=version.id,
            scope={
                "workspace_id": doc.workspace_id,
                "subject_id": doc.subject_id,
                "folder_id": doc.folder_id,
                "chapter_id": doc.chapter_id,
            },
            rows=_build_rows(drafts, extraction.ocr_mean_confidence),
            index_version=deps.settings.embedding_index_version,
        )
        mean = extraction.ocr_mean_confidence
        await docs.set_version_status(
            doc=doc,
            version=version,
            status="completed",
            extraction_method=extraction.method,
            ocr_used=extraction.ocr_used,
            ocr_mean_confidence=round(mean, 1) if mean is not None else None,
            page_count=extraction.page_count,
            slide_count=extraction.slide_count,
            word_count=words,
            warnings=list(extraction.warnings),
            pipeline_version=PIPELINE_VERSION,
            index_version=deps.settings.embedding_index_version,
        )
        await docs.activate_version(doc, version)
        await ProcessingJobRepository(db).finish(job_id, "succeeded", None, _now())
        await db.commit()
        return len(drafts)


async def run_job(
    deps: PipelineDeps, job_id: uuid.UUID, *, celery_task_id: str | None = None
) -> str:
    started = time.monotonic()
    async with deps.session_factory() as db:
        jobs = ProcessingJobRepository(db)
        try:
            job = await jobs.claim(job_id, _now(), celery_task_id)
            await db.commit()
        except IntegrityError:  # another job of this version is running: leave this one queued
            await db.rollback()
            return SKIPPED
        if job is None:
            return SKIPPED
        user_id, version_id = job.user_id, job.document_version_id
        docs = DocumentRepository(db)
        version = await docs.get_version_by_id(version_id=version_id, user_id=user_id)
        doc = (
            await docs.get_owned(document_id=version.document_id, user_id=user_id)
            if version
            else None
        )
        if version is None or doc is None:
            return SKIPPED
        storage_key, file_type, checksum = version.storage_key, doc.file_type, version.checksum
        await docs.set_version_status(doc=doc, version=version, status="validating")
        await db.commit()

    try:
        spool = await _read_object(deps.storage, storage_key, deps.settings.doc_max_file_bytes)
        try:
            import hashlib

            digest = hashlib.sha256()
            while block := spool.read(_CHUNK):
                digest.update(block)
            if digest.hexdigest() != checksum:
                raise ExtractionError(FILE_CHECKSUM_MISMATCH)
            spool.seek(0)
            detected = detect_and_validate(
                cast(BinaryIO, spool),
                {"jpg": "jpg"}.get(file_type, file_type),
                _upload_limits(deps.settings),
            )
            if detected.file_type != file_type:
                raise ExtractionError(FILE_CHECKSUM_MISMATCH)
            spool.seek(0)
            data = spool.read()
        finally:
            spool.close()
        await _check_cancel(deps, job_id)

        await _set_status(
            deps,
            job_id,
            user_id,
            version_id,
            "ocr_processing" if file_type in ("png", "jpg") else "extracting",
            "extracting",
        )
        extraction = await asyncio.to_thread(extract, file_type, data, _limits(deps.settings))
        del data
        await _check_cancel(deps, job_id)

        await _set_status(deps, job_id, user_id, version_id, "normalising", "normalising")
        blocks = normalise_blocks(extraction.blocks, extraction.page_count)
        words = word_count(blocks)
        await _set_status(deps, job_id, user_id, version_id, "chunking", "chunking")
        cfg = ChunkSettings(
            deps.settings.doc_chunk_target_tokens,
            deps.settings.doc_chunk_overlap_tokens,
            deps.settings.doc_chunk_max_tokens,
        )
        drafts = chunk_blocks(blocks, cfg)
        if not drafts:
            raise ExtractionError("NO_TEXT_FOUND", "No text could be extracted from the document.")
        await _check_cancel(deps, job_id)

        # M4 plugs the embedding stage in here (before the write transaction, D-68).
        await _set_status(deps, job_id, user_id, version_id, "indexing", "indexing")
        chunk_count = await _write(
            deps,
            job_id=job_id,
            user_id=user_id,
            version_id=version_id,
            extraction=extraction,
            drafts=drafts,
            words=words,
        )
    except JobCancelledError:
        await _finish_failed(deps, job_id, user_id, version_id, "CANCELLED", status="cancelled")
        logger.info("document_job_cancelled", job_id=str(job_id))
        return CANCELLED
    except ExtractionError as exc:
        return await _fail(deps, job_id, user_id, version_id, exc.code, started)
    except UploadRejected as exc:
        return await _fail(deps, job_id, user_id, version_id, exc.code, started)
    except StorageNotFoundError as exc:
        return await _fail(deps, job_id, user_id, version_id, exc.code, started)
    except StorageError as exc:
        return await _transient(deps, job_id, user_id, version_id, exc.code, started)
    except SoftTimeLimitExceeded:
        return await _fail(deps, job_id, user_id, version_id, errors.TASK_TIMEOUT, started)
    except MemoryError:
        return await _fail(deps, job_id, user_id, version_id, "MEMORY_LIMIT", started)
    except Exception as exc:
        logger.error("document_job_error", job_id=str(job_id), error_type=type(exc).__name__)
        return await _fail(deps, job_id, user_id, version_id, errors.INTERNAL, started)
    logger.info(
        "document_job_succeeded",
        job_id=str(job_id),
        chunks=chunk_count,
        words=words,
        ocr_used=extraction.ocr_used,
        duration_ms=int((time.monotonic() - started) * 1000),
    )
    return SUCCEEDED


async def _fail(
    deps: PipelineDeps,
    job_id: uuid.UUID,
    user_id: uuid.UUID,
    version_id: uuid.UUID,
    code: str,
    started: float,
) -> str:
    await _finish_failed(deps, job_id, user_id, version_id, code)
    logger.warning(
        "document_job_failed",
        job_id=str(job_id),
        error_code=code,
        duration_ms=int((time.monotonic() - started) * 1000),
    )
    return FAILED


async def _transient(
    deps: PipelineDeps,
    job_id: uuid.UUID,
    user_id: uuid.UUID,
    version_id: uuid.UUID,
    code: str,
    started: float,
) -> str:
    """Storage briefly unavailable: requeue with a retry count, or fail once retries are used up."""
    async with deps.session_factory() as db:
        job = await ProcessingJobRepository(db).get(job_id)
        retries = job.retry_count if job else deps.settings.celery_max_retries
        if retries >= deps.settings.celery_max_retries:
            await db.rollback()
            return await _fail(deps, job_id, user_id, version_id, code, started)
        await ProcessingJobRepository(db).requeue_for_retry(job_id)
        docs = DocumentRepository(db)
        version = await docs.get_version_by_id(version_id=version_id, user_id=user_id)
        if version is not None:
            doc = await docs.get_owned(document_id=version.document_id, user_id=user_id)
            if doc is not None:
                await docs.set_version_status(doc=doc, version=version, status="queued")
        await db.commit()
    logger.warning("document_job_requeued", job_id=str(job_id), error_code=code)
    return RETRY


# Re-exported so tasks can type the callable they hand to Celery.
RunJob = Callable[[PipelineDeps, uuid.UUID], Awaitable[str]]
