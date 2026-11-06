from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentVersion
from app.models.document_processing_job import DocumentProcessingJob


class ProcessingJobRepository:
    """SQL for processing jobs. M1 only needs the stale-job sweep; the pipeline arrives in M3."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def fail_stale_running(self, cutoff: datetime, now: datetime, error_code: str) -> int:
        """Fail `running` jobs whose last sign of life is older than `cutoff`.

        Also sets the version to `failed` and mirrors that on the document when the version is the
        latest one (D-68: version status authoritative, document status a copy). Returns the count.
        """
        last_seen = func.coalesce(
            DocumentProcessingJob.heartbeat_at,
            DocumentProcessingJob.started_at,
            DocumentProcessingJob.created_at,
        )
        stale = (
            select(
                DocumentProcessingJob.id,
                DocumentProcessingJob.document_id,
                DocumentProcessingJob.document_version_id,
            )
            .where(DocumentProcessingJob.status == "running", last_seen < cutoff)
            .with_for_update(skip_locked=True)
        )
        rows = (await self._db.execute(stale)).all()
        if not rows:
            return 0
        job_ids = [r.id for r in rows]
        version_ids = [r.document_version_id for r in rows]
        await self._db.execute(
            update(DocumentProcessingJob)
            .where(DocumentProcessingJob.id.in_(job_ids))
            .values(status="failed", error_code=error_code, completed_at=now)
        )
        await self._db.execute(
            update(DocumentVersion)
            .where(DocumentVersion.id.in_(version_ids))
            .values(processing_status="failed")
        )
        latest = (
            select(DocumentVersion.document_id)
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(
                DocumentVersion.id.in_(version_ids),
                DocumentVersion.version_number == Document.latest_version,
            )
        )
        await self._db.execute(
            update(Document).where(Document.id.in_(latest)).values(processing_status="failed")
        )
        return len(rows)
