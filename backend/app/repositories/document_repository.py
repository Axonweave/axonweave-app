import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentVersion
from app.models.document_chunk import DocumentChunk
from app.models.document_processing_job import DocumentProcessingJob

# Allow-listed sort columns (rule 4): nothing user-supplied reaches an ORDER BY.
_SORT_COLUMNS = {
    "created_at": Document.created_at,
    "updated_at": Document.updated_at,
    "display_name": Document.display_name,
    "file_size": Document.file_size,
}
SORT_FIELDS = tuple(_SORT_COLUMNS)


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class DocumentRepository:
    """SQL for documents. Every read is scoped by `user_id`; other users' rows never load."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ── reads ────────────────────────────────────────────────────────────────

    async def get_owned(self, *, document_id: uuid.UUID, user_id: uuid.UUID) -> Document | None:
        result = await self._db.execute(
            select(Document).where(Document.id == document_id, Document.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_version(
        self, *, document_id: uuid.UUID, user_id: uuid.UUID, version_number: int
    ) -> DocumentVersion | None:
        result = await self._db.execute(
            select(DocumentVersion).where(
                DocumentVersion.document_id == document_id,
                DocumentVersion.user_id == user_id,
                DocumentVersion.version_number == version_number,
            )
        )
        return result.scalar_one_or_none()

    async def latest_job(
        self, *, document_version_id: uuid.UUID, user_id: uuid.UUID
    ) -> DocumentProcessingJob | None:
        result = await self._db.execute(
            select(DocumentProcessingJob)
            .where(
                DocumentProcessingJob.document_version_id == document_version_id,
                DocumentProcessingJob.user_id == user_id,
            )
            .order_by(DocumentProcessingJob.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    def _filtered(
        self,
        stmt: Select,  # type: ignore[type-arg]
        *,
        user_id: uuid.UUID,
        workspace_id: uuid.UUID | None,
        subject_id: uuid.UUID | None,
        folder_id: uuid.UUID | None,
        chapter_id: uuid.UUID | None,
        status: str | None,
        file_type: str | None,
        q: str | None,
        include_archived: bool,
    ) -> Select:  # type: ignore[type-arg]
        stmt = stmt.where(Document.user_id == user_id)
        if workspace_id is not None:
            stmt = stmt.where(Document.workspace_id == workspace_id)
        if subject_id is not None:
            stmt = stmt.where(Document.subject_id == subject_id)
        if folder_id is not None:
            stmt = stmt.where(Document.folder_id == folder_id)
        if chapter_id is not None:
            stmt = stmt.where(Document.chapter_id == chapter_id)
        if status is not None:
            stmt = stmt.where(Document.processing_status == status)
        if file_type is not None:
            stmt = stmt.where(Document.file_type == file_type)
        if q:
            stmt = stmt.where(
                func.lower(Document.display_name).like(f"%{_escape_like(q.lower())}%", escape="\\")
            )
        if not include_archived:
            stmt = stmt.where(Document.archived_at.is_(None))
        return stmt

    async def list_for_user(
        self,
        *,
        user_id: uuid.UUID,
        workspace_id: uuid.UUID | None = None,
        subject_id: uuid.UUID | None = None,
        folder_id: uuid.UUID | None = None,
        chapter_id: uuid.UUID | None = None,
        status: str | None = None,
        file_type: str | None = None,
        q: str | None = None,
        include_archived: bool = False,
        sort_by: str = "created_at",
        sort_dir: str = "desc",
        limit: int = 25,
        offset: int = 0,
    ) -> tuple[list[Document], int]:
        filters: dict[str, Any] = {
            "user_id": user_id,
            "workspace_id": workspace_id,
            "subject_id": subject_id,
            "folder_id": folder_id,
            "chapter_id": chapter_id,
            "status": status,
            "file_type": file_type,
            "q": q,
            "include_archived": include_archived,
        }
        column = _SORT_COLUMNS.get(sort_by, Document.created_at)
        order = column.asc() if sort_dir == "asc" else column.desc()
        rows = (
            await self._db.execute(
                self._filtered(select(Document), **filters)
                .order_by(order, Document.id)
                .limit(limit)
                .offset(offset)
            )
        ).scalars()
        total = (
            await self._db.execute(self._filtered(select(func.count(Document.id)), **filters))
        ).scalar_one()
        return list(rows), total

    async def usage_for_user(self, user_id: uuid.UUID) -> tuple[int, int]:
        """(document count, total bytes) for quota checks, counted in the database (D-71)."""
        row = (
            await self._db.execute(
                select(
                    func.count(Document.id), func.coalesce(func.sum(Document.file_size), 0)
                ).where(Document.user_id == user_id)
            )
        ).one()
        return int(row[0]), int(row[1])

    # ── writes ───────────────────────────────────────────────────────────────

    async def create_with_version_and_job(
        self,
        *,
        document_id: uuid.UUID,
        user_id: uuid.UUID,
        workspace_id: uuid.UUID,
        subject_id: uuid.UUID | None,
        folder_id: uuid.UUID | None,
        chapter_id: uuid.UUID | None,
        display_name: str,
        original_filename: str,
        file_type: str,
        mime_type: str,
        file_size: int,
        checksum: str,
        storage_key: str,
        pipeline_version: str,
    ) -> tuple[Document, uuid.UUID]:
        """Insert the document, version 1 and a queued job in one flush; the caller commits."""
        doc = Document(
            id=document_id,
            user_id=user_id,
            workspace_id=workspace_id,
            subject_id=subject_id,
            folder_id=folder_id,
            chapter_id=chapter_id,
            display_name=display_name,
            original_filename=original_filename,
            file_type=file_type,
            mime_type=mime_type,
            file_size=file_size,
            checksum=checksum,
            processing_status="queued",
            active_version=None,
            latest_version=1,
        )
        self._db.add(doc)
        await self._db.flush()
        version = DocumentVersion(
            document_id=document_id,
            user_id=user_id,
            version_number=1,
            storage_key=storage_key,
            file_size=file_size,
            checksum=checksum,
            processing_status="queued",
        )
        self._db.add(version)
        await self._db.flush()
        job = DocumentProcessingJob(
            user_id=user_id,
            document_id=document_id,
            document_version_id=version.id,
            pipeline_version=pipeline_version,
            status="queued",
            stage="queued",
        )
        self._db.add(job)
        await self._db.flush()
        return doc, job.id

    async def add_version_and_job(
        self,
        doc: Document,
        *,
        version_number: int,
        storage_key: str,
        file_size: int,
        checksum: str,
        pipeline_version: str,
    ) -> uuid.UUID:
        """Add a queued version and job. `active_version` is not touched: the old version stays
        the searchable one until the new one completes. The caller commits."""
        version = DocumentVersion(
            document_id=doc.id,
            user_id=doc.user_id,
            version_number=version_number,
            storage_key=storage_key,
            file_size=file_size,
            checksum=checksum,
            processing_status="queued",
        )
        self._db.add(version)
        await self._db.flush()
        job = DocumentProcessingJob(
            user_id=doc.user_id,
            document_id=doc.id,
            document_version_id=version.id,
            pipeline_version=pipeline_version,
            status="queued",
            stage="queued",
        )
        self._db.add(job)
        doc.latest_version = version_number
        doc.file_size = file_size
        doc.checksum = checksum
        doc.processing_status = "queued"
        await self._db.flush()
        return job.id

    async def move(
        self,
        doc: Document,
        *,
        workspace_id: uuid.UUID,
        subject_id: uuid.UUID | None,
        folder_id: uuid.UUID | None,
        chapter_id: uuid.UUID | None,
    ) -> Document:
        """Change placement and keep the chunks' scope columns in step (they are filters only)."""
        doc.workspace_id = workspace_id
        doc.subject_id = subject_id
        doc.folder_id = folder_id
        doc.chapter_id = chapter_id
        await self._db.flush()
        await self._db.execute(
            update(DocumentChunk)
            .where(DocumentChunk.document_id == doc.id, DocumentChunk.user_id == doc.user_id)
            .values(
                workspace_id=workspace_id,
                subject_id=subject_id,
                folder_id=folder_id,
                chapter_id=chapter_id,
            )
        )
        return doc

    async def rename(self, doc: Document, display_name: str) -> Document:
        doc.display_name = display_name
        await self._db.flush()
        return doc

    async def set_archived(self, doc: Document, archived: bool) -> Document:
        doc.archived_at = datetime.now(UTC) if archived else None
        await self._db.flush()
        return doc

    # ── deletion support (D-66) ──────────────────────────────────────────────

    async def storage_keys_for_document(
        self, *, document_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[str]:
        rows = await self._db.execute(
            select(DocumentVersion.storage_key).where(
                DocumentVersion.document_id == document_id, DocumentVersion.user_id == user_id
            )
        )
        return list(rows.scalars().all())

    async def storage_keys_for_subject(self, subject_id: uuid.UUID) -> list[str]:
        """Called by the subject delete path, which has already proved the subject is owned."""
        rows = await self._db.execute(
            select(DocumentVersion.storage_key)
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(Document.subject_id == subject_id)
        )
        return list(rows.scalars().all())

    async def storage_keys_for_workspace(self, workspace_id: uuid.UUID) -> list[str]:
        rows = await self._db.execute(
            select(DocumentVersion.storage_key)
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(Document.workspace_id == workspace_id)
        )
        return list(rows.scalars().all())

    async def storage_keys_for_user(self, user_id: uuid.UUID) -> list[str]:
        rows = await self._db.execute(
            select(DocumentVersion.storage_key).where(DocumentVersion.user_id == user_id)
        )
        return list(rows.scalars().all())

    async def delete_owned(self, *, document_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        result = await self._db.execute(
            delete(Document).where(Document.id == document_id, Document.user_id == user_id)
        )
        return bool(result.rowcount)

    async def export_rows(self, user_id: uuid.UUID) -> Sequence[Document]:
        rows = await self._db.execute(
            select(Document).where(Document.user_id == user_id).order_by(Document.created_at)
        )
        return rows.scalars().all()

    # ── pipeline support (M3): all scoped by the job's user_id ───────────────

    async def get_version_by_id(
        self, *, version_id: uuid.UUID, user_id: uuid.UUID
    ) -> DocumentVersion | None:
        result = await self._db.execute(
            select(DocumentVersion).where(
                DocumentVersion.id == version_id, DocumentVersion.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def set_version_status(
        self, *, doc: Document, version: DocumentVersion, status: str, **fields: Any
    ) -> None:
        """Version status is authoritative; the document copy follows only the latest version
        (D-68)."""
        version.processing_status = status
        for name, value in fields.items():
            setattr(version, name, value)
        if version.version_number == doc.latest_version:
            doc.processing_status = status
        await self._db.flush()

    async def activate_version(self, doc: Document, version: DocumentVersion) -> None:
        """Make this version the searchable one (one transaction with the chunk swap)."""
        doc.active_version = version.version_number
        await self._db.flush()
        # Older versions stop being searchable now; their chunks are dropped in the same
        # transaction (their files stay, so the history is kept).
        await self._db.execute(
            delete(DocumentChunk).where(
                DocumentChunk.document_id == doc.id,
                DocumentChunk.user_id == doc.user_id,
                DocumentChunk.document_version_id != version.id,
            )
        )
