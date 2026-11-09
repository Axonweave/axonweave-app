import hashlib
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from app.core.config import Settings
from app.ingestion.dispatch import JobDispatcher, get_job_dispatcher
from app.ingestion.version import PIPELINE_VERSION
from app.models.document import Document, DocumentVersion
from app.models.document_chunk import DocumentChunk
from app.models.document_processing_job import DocumentProcessingJob
from app.models.user import User
from app.modules.documents import cleanup
from app.modules.documents.scanner import Scanner, ScannerUnavailableError
from app.modules.documents.schemas import Placement
from app.modules.documents.upload import UploadForm
from app.modules.documents.validation import (
    CHUNK,
    Limits,
    UploadRejected,
    detect_and_validate,
    extension_of,
    sanitise_display_name,
)
from app.repositories.chapter_repository import ChapterRepository
from app.repositories.document_chunk_repository import DocumentChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.folder_repository import FolderRepository
from app.repositories.processing_job_repository import ProcessingJobRepository
from app.repositories.subject_repository import SubjectRepository
from app.repositories.workspace_repository import WorkspaceRepository
from app.storage.base import StorageBackend, StorageError
from app.storage.keys import build_original_key

logger = structlog.get_logger(__name__)


def _not_found(code: str, message: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": code, "message": message})


@dataclass
class UploadOutcome:
    documents: list[Document] = field(default_factory=list)
    rejected: list[tuple[str, UploadRejected]] = field(default_factory=list)


@dataclass
class Download:
    document: Document
    stream: AsyncIterator[bytes]


class DocumentService:
    def __init__(
        self,
        db: AsyncSession,
        storage: StorageBackend,
        scanner: Scanner,
        settings: Settings,
        dispatcher: JobDispatcher | None = None,
    ) -> None:
        self._dispatcher = dispatcher or get_job_dispatcher()
        self._jobs = ProcessingJobRepository(db)
        self._chunks = DocumentChunkRepository(db)
        self._db = db
        self._storage = storage
        self._scanner = scanner
        self._settings = settings
        self._docs = DocumentRepository(db)
        self._workspaces = WorkspaceRepository(db)
        self._subjects = SubjectRepository(db)
        self._folders = FolderRepository(db)
        self._chapters = ChapterRepository(db)
        self._limits = Limits(
            max_file_bytes=settings.doc_max_file_bytes,
            zip_max_entries=settings.doc_zip_max_entries,
            zip_max_uncompressed_bytes=settings.doc_zip_max_uncompressed_bytes,
            zip_max_ratio=settings.doc_zip_max_ratio,
            image_max_pixels=settings.doc_image_max_pixels,
        )

    # ── placement: every parent in the chain must belong to this user ────────

    async def resolve_placement(self, *, user_id: uuid.UUID, placement: Placement) -> Placement:
        if await self._workspaces.get_for_user(placement.workspace_id, user_id) is None:
            raise _not_found("WORKSPACE_NOT_FOUND", "Workspace not found.")
        if placement.subject_id is None:
            if placement.folder_id or placement.chapter_id:
                raise HTTPException(
                    422,
                    detail={
                        "code": "INVALID_PLACEMENT",
                        "message": "A folder or chapter needs a subject.",
                    },
                )
            return placement
        subject = await self._subjects.get_for_workspace(
            subject_id=placement.subject_id, workspace_id=placement.workspace_id
        )
        if subject is None:
            raise _not_found("SUBJECT_NOT_FOUND", "Subject not found.")
        if placement.folder_id and not await self._folders.get_for_subject(
            folder_id=placement.folder_id, subject_id=subject.id
        ):
            raise _not_found("FOLDER_NOT_FOUND", "Folder not found.")
        if placement.chapter_id and not await self._chapters.get_for_subject(
            chapter_id=placement.chapter_id, subject_id=subject.id
        ):
            raise _not_found("CHAPTER_NOT_FOUND", "Chapter not found.")
        return placement

    # ── upload ───────────────────────────────────────────────────────────────

    async def upload(self, *, user: User, form: UploadForm) -> UploadOutcome:
        placement = await self.resolve_placement(
            user_id=user.id,
            placement=Placement(
                workspace_id=form.workspace_id,
                subject_id=form.subject_id,
                folder_id=form.folder_id,
                chapter_id=form.chapter_id,
            ),
        )
        count, total_bytes = await self._docs.usage_for_user(user.id)
        outcome = UploadOutcome()
        for part in form.files:
            display = sanitise_display_name(part.filename)
            try:
                doc = await self._store_one(
                    user=user,
                    placement=placement,
                    part=part,
                    display=display,
                    count=count,
                    total_bytes=total_bytes,
                )
            except UploadRejected as exc:
                outcome.rejected.append((display, exc))
                continue
            count += 1
            total_bytes += doc.file_size
            outcome.documents.append(doc)
        return outcome

    async def _store_one(
        self,
        *,
        user: User,
        placement: Placement,
        part: UploadFile,
        display: str,
        count: int,
        total_bytes: int,
    ) -> Document:
        f = part.file
        detected = detect_and_validate(f, extension_of(display), self._limits)
        size = f.seek(0, 2)
        f.seek(0)
        if count >= self._settings.doc_max_documents_per_user:
            raise UploadRejected("DOCUMENT_QUOTA_EXCEEDED", "Document limit reached.", 409)
        if total_bytes + size > self._settings.doc_max_total_bytes_per_user:
            raise UploadRejected("STORAGE_QUOTA_EXCEEDED", "Storage limit reached.", 409)
        try:
            await self._scanner.scan(f)
        except ScannerUnavailableError:
            raise UploadRejected(
                "SCANNER_UNAVAILABLE", "Uploads are temporarily unavailable.", 503
            ) from None
        f.seek(0)

        digest = hashlib.sha256()
        while chunk := await run_in_threadpool(f.read, CHUNK):
            digest.update(chunk)
        f.seek(0)

        document_id = uuid.uuid4()
        key = build_original_key(user.id, document_id, 1, detected.file_type)

        async def chunks() -> AsyncIterator[bytes]:
            while block := await run_in_threadpool(f.read, CHUNK):
                yield block

        try:
            await self._storage.put(
                key,
                chunks(),
                content_type=detected.mime_type,
                max_bytes=self._limits.max_file_bytes,
            )
        except StorageError as exc:
            logger.error("document_store_failed", code=exc.code)
            raise UploadRejected("STORAGE_UNAVAILABLE", "Storage is unavailable.", 503) from None
        try:
            doc, job_id = await self._docs.create_with_version_and_job(
                document_id=document_id,
                user_id=user.id,
                workspace_id=placement.workspace_id,
                subject_id=placement.subject_id,
                folder_id=placement.folder_id,
                chapter_id=placement.chapter_id,
                display_name=display,
                original_filename=display,
                file_type=detected.file_type,
                mime_type=detected.mime_type,
                file_size=size,
                checksum=digest.hexdigest(),
                storage_key=key,
                pipeline_version=PIPELINE_VERSION,
            )
            await self._db.commit()
        except Exception:
            await self._db.rollback()
            try:  # do not leave an orphan object behind when the row could not be written
                await self._storage.delete(key)
            except StorageError as exc:
                logger.error("document_orphan_cleanup_failed", code=exc.code)
            raise
        await self._dispatch(job_id)
        logger.info(
            "document_uploaded",
            user_id=str(user.id),
            document_id=str(document_id),
            file_type=detected.file_type,
            size=size,
        )
        return doc

    # ── reads and updates ────────────────────────────────────────────────────

    async def get_owned(self, *, user_id: uuid.UUID, document_id: uuid.UUID) -> Document:
        doc = await self._docs.get_owned(document_id=document_id, user_id=user_id)
        if doc is None:
            raise _not_found("DOCUMENT_NOT_FOUND", "Document not found.")
        return doc

    async def list_documents(
        self, *, user_id: uuid.UUID, **filters: Any
    ) -> tuple[list[Document], int]:
        # Every filter is applied together with user_id in SQL: a foreign id simply matches nothing.
        return await self._docs.list_for_user(user_id=user_id, **filters)

    async def update(
        self,
        *,
        user_id: uuid.UUID,
        document_id: uuid.UUID,
        display_name: str | None,
        placement: Placement | None,
    ) -> Document:
        doc = await self.get_owned(user_id=user_id, document_id=document_id)
        if placement is not None:
            resolved = await self.resolve_placement(user_id=user_id, placement=placement)
            await self._docs.move(
                doc,
                workspace_id=resolved.workspace_id,
                subject_id=resolved.subject_id,
                folder_id=resolved.folder_id,
                chapter_id=resolved.chapter_id,
            )
        if display_name is not None:
            await self._docs.rename(doc, display_name)
        await self._db.commit()
        await self._db.refresh(doc)
        return doc

    async def set_archived(
        self, *, user_id: uuid.UUID, document_id: uuid.UUID, archived: bool
    ) -> Document:
        doc = await self.get_owned(user_id=user_id, document_id=document_id)
        await self._docs.set_archived(doc, archived)
        await self._db.commit()
        await self._db.refresh(doc)
        return doc

    async def delete(self, *, user_id: uuid.UUID, document_id: uuid.UUID) -> None:
        await self.get_owned(user_id=user_id, document_id=document_id)
        # Outbox rows and the delete share one transaction (D-66).
        await cleanup.enqueue_for_document(self._db, document_id=document_id, user_id=user_id)
        await self._docs.delete_owned(document_id=document_id, user_id=user_id)
        await self._db.commit()
        logger.info("document_deleted", user_id=str(user_id), document_id=str(document_id))

    async def processing_status(
        self, *, user_id: uuid.UUID, document_id: uuid.UUID
    ) -> tuple[Document, DocumentVersion | None, DocumentProcessingJob | None]:
        doc = await self.get_owned(user_id=user_id, document_id=document_id)
        version = await self._docs.get_version(
            document_id=doc.id, user_id=user_id, version_number=doc.latest_version
        )
        job = (
            await self._docs.latest_job(document_version_id=version.id, user_id=user_id)
            if version
            else None
        )
        return doc, version, job

    async def open_original(self, *, user_id: uuid.UUID, document_id: uuid.UUID) -> Download:
        """Ownership first, then the bytes stream (D-64). The storage key never leaves here."""
        doc = await self.get_owned(user_id=user_id, document_id=document_id)
        version = await self._docs.get_version(
            document_id=doc.id, user_id=user_id, version_number=doc.latest_version
        )
        if version is None:
            raise _not_found("DOCUMENT_NOT_FOUND", "Document not found.")
        try:
            present = await self._storage.exists(version.storage_key)
        except StorageError as exc:
            logger.error("document_read_failed", code=exc.code)
            raise HTTPException(
                503, detail={"code": "STORAGE_UNAVAILABLE", "message": "Storage is unavailable."}
            ) from None
        if not present:  # row without object: report it before any header is sent
            logger.error("document_object_missing", document_id=str(doc.id))
            raise _not_found("DOCUMENT_FILE_MISSING", "The document file is not available.")
        return Download(document=doc, stream=self._storage.open(version.storage_key))

    # -- processing control (M3) ---------------------------------------------

    async def _dispatch(self, job_id: uuid.UUID) -> None:
        """Best effort: a job the broker did not take stays queued and the sweeper sends it."""
        await run_in_threadpool(self._dispatcher.dispatch, job_id)

    def require_processing(self) -> None:
        if not self._dispatcher.available():
            raise HTTPException(
                503,
                detail={
                    "code": "PROCESSING_UNAVAILABLE",
                    "message": "Document processing is not available.",
                },
            )

    async def _latest_version(self, doc: Document) -> DocumentVersion:
        version = await self._docs.get_version(
            document_id=doc.id, user_id=doc.user_id, version_number=doc.latest_version
        )
        if version is None:
            raise _not_found("DOCUMENT_NOT_FOUND", "Document not found.")
        return version

    async def _requeue(
        self, *, user_id: uuid.UUID, document_id: uuid.UUID, allowed: tuple[str, ...], code: str
    ) -> Document:
        self.require_processing()
        doc = await self.get_owned(user_id=user_id, document_id=document_id)
        version = await self._latest_version(doc)
        if await self._jobs.active_for_version(version.id) is not None:
            raise HTTPException(
                409,
                detail={"code": "PROCESSING_IN_PROGRESS", "message": "Processing is in progress."},
            )
        if version.processing_status not in allowed:
            raise HTTPException(
                409, detail={"code": code, "message": "This document cannot be processed now."}
            )
        job = await self._jobs.create_queued(
            user_id=user_id, document_id=doc.id, version_id=version.id, pipeline=PIPELINE_VERSION
        )
        await self._docs.set_version_status(doc=doc, version=version, status="queued")
        await self._db.commit()
        await self._dispatch(job.id)
        await self._db.refresh(doc)
        return doc

    async def retry(self, *, user_id: uuid.UUID, document_id: uuid.UUID) -> Document:
        return await self._requeue(
            user_id=user_id,
            document_id=document_id,
            allowed=("failed", "cancelled"),
            code="NOT_RETRYABLE",
        )

    async def reprocess(self, *, user_id: uuid.UUID, document_id: uuid.UUID) -> Document:
        return await self._requeue(
            user_id=user_id,
            document_id=document_id,
            allowed=("completed", "failed", "cancelled"),
            code="NOT_REPROCESSABLE",
        )

    async def cancel(self, *, user_id: uuid.UUID, document_id: uuid.UUID) -> Document:
        doc = await self.get_owned(user_id=user_id, document_id=document_id)
        version = await self._latest_version(doc)
        job = await self._jobs.active_for_version(version.id)
        if job is None:
            raise HTTPException(
                409, detail={"code": "NOTHING_TO_CANCEL", "message": "Nothing is processing."}
            )
        if job.status == "queued":  # not started: cancel right away
            await self._jobs.finish(job.id, "cancelled", None, datetime.now(UTC))
            await self._docs.set_version_status(doc=doc, version=version, status="cancelled")
        else:  # running: the worker stops at the next stage boundary
            await self._jobs.request_cancel(job.id)
        await self._db.commit()
        await self._db.refresh(doc)
        return doc

    async def processing_details(
        self, *, user_id: uuid.UUID, document_id: uuid.UUID
    ) -> tuple[Document, DocumentVersion, list[DocumentProcessingJob], int]:
        doc = await self.get_owned(user_id=user_id, document_id=document_id)
        version = await self._latest_version(doc)
        jobs = await self._jobs.history(version_id=version.id, user_id=user_id)
        count = await self._chunks.count_for_version(user_id=user_id, version_id=version.id)
        return doc, version, jobs, count

    async def _readable_version(self, doc: Document) -> DocumentVersion:
        if doc.active_version is None:
            raise HTTPException(
                409,
                detail={"code": "DOCUMENT_NOT_READY", "message": "The document is not processed."},
            )
        version = await self._docs.get_version(
            document_id=doc.id, user_id=doc.user_id, version_number=doc.active_version
        )
        if version is None:
            raise _not_found("DOCUMENT_NOT_FOUND", "Document not found.")
        return version

    async def pages(self, *, user_id: uuid.UUID, document_id: uuid.UUID) -> list[dict[str, Any]]:
        doc = await self.get_owned(user_id=user_id, document_id=document_id)
        version = await self._readable_version(doc)
        return await self._chunks.pages(user_id=user_id, document_id=doc.id, version_id=version.id)

    async def content(
        self,
        *,
        user_id: uuid.UUID,
        document_id: uuid.UUID,
        page: int | None,
        slide: int | None,
        limit: int,
        offset: int,
    ) -> tuple[list[DocumentChunk], int]:
        doc = await self.get_owned(user_id=user_id, document_id=document_id)
        version = await self._readable_version(doc)
        return await self._chunks.content(
            user_id=user_id,
            document_id=doc.id,
            version_id=version.id,
            page=page,
            slide=slide,
            limit=limit,
            offset=offset,
        )
