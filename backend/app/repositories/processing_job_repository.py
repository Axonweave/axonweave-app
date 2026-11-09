import uuid
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

    # ── M3: lifecycle used by the pipeline and the dispatch sweeper ──────────

    async def create_queued(
        self, *, user_id: uuid.UUID, document_id: uuid.UUID, version_id: uuid.UUID, pipeline: str
    ) -> DocumentProcessingJob:
        job = DocumentProcessingJob(
            user_id=user_id,
            document_id=document_id,
            document_version_id=version_id,
            pipeline_version=pipeline,
            status="queued",
            stage="queued",
        )
        self._db.add(job)
        await self._db.flush()
        return job

    async def get(self, job_id: uuid.UUID) -> DocumentProcessingJob | None:
        result = await self._db.execute(
            select(DocumentProcessingJob).where(DocumentProcessingJob.id == job_id)
        )
        return result.scalar_one_or_none()

    async def active_for_version(self, version_id: uuid.UUID) -> DocumentProcessingJob | None:
        result = await self._db.execute(
            select(DocumentProcessingJob)
            .where(
                DocumentProcessingJob.document_version_id == version_id,
                DocumentProcessingJob.status.in_(("queued", "running")),
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def claim(
        self, job_id: uuid.UUID, now: datetime, celery_task_id: str | None
    ) -> DocumentProcessingJob | None:
        """queued -> running in one statement. None when another worker already took it, or the
        job is no longer queued (duplicate delivery). The partial unique index additionally stops
        two jobs of one version running at once."""
        result = await self._db.execute(
            update(DocumentProcessingJob)
            .where(DocumentProcessingJob.id == job_id, DocumentProcessingJob.status == "queued")
            .values(
                status="running",
                stage="validating",
                started_at=now,
                heartbeat_at=now,
                celery_task_id=celery_task_id,
            )
            .returning(DocumentProcessingJob.id)
        )
        if result.scalar_one_or_none() is None:
            return None
        return await self.get(job_id)

    async def set_stage(self, job_id: uuid.UUID, stage: str, now: datetime) -> None:
        await self._db.execute(
            update(DocumentProcessingJob)
            .where(DocumentProcessingJob.id == job_id)
            .values(stage=stage, heartbeat_at=now)
        )

    async def cancel_requested(self, job_id: uuid.UUID) -> bool:
        value = await self._db.execute(
            select(DocumentProcessingJob.cancel_requested).where(DocumentProcessingJob.id == job_id)
        )
        return bool(value.scalar_one_or_none())

    async def finish(
        self, job_id: uuid.UUID, status: str, error_code: str | None, now: datetime
    ) -> None:
        await self._db.execute(
            update(DocumentProcessingJob)
            .where(DocumentProcessingJob.id == job_id)
            .values(
                status=status,
                stage="done" if status == "succeeded" else status,
                error_code=error_code,
                completed_at=now,
            )
        )

    async def requeue_for_retry(self, job_id: uuid.UUID) -> int:
        """Back to queued with retry_count + 1 after a transient failure. Returns the new count."""
        result = await self._db.execute(
            update(DocumentProcessingJob)
            .where(DocumentProcessingJob.id == job_id)
            .values(
                status="queued",
                stage="queued",
                retry_count=DocumentProcessingJob.retry_count + 1,
                started_at=None,
                heartbeat_at=None,
            )
            .returning(DocumentProcessingJob.retry_count)
        )
        return int(result.scalar_one())

    async def request_cancel(self, job_id: uuid.UUID) -> None:
        await self._db.execute(
            update(DocumentProcessingJob)
            .where(DocumentProcessingJob.id == job_id)
            .values(cancel_requested=True)
        )

    async def queued_older_than(self, cutoff: datetime, limit: int) -> list[uuid.UUID]:
        """Jobs that were committed but never delivered (broker was down) or were lost."""
        rows = await self._db.execute(
            select(DocumentProcessingJob.id)
            .where(
                DocumentProcessingJob.status == "queued", DocumentProcessingJob.updated_at < cutoff
            )
            .order_by(DocumentProcessingJob.created_at)
            .limit(limit)
        )
        return list(rows.scalars().all())

    async def touch(self, job_id: uuid.UUID, now: datetime) -> None:
        """Mark a queued job as just dispatched so the sweeper does not re-send it every minute."""
        await self._db.execute(
            update(DocumentProcessingJob)
            .where(DocumentProcessingJob.id == job_id)
            .values(updated_at=now)
        )

    async def history(
        self, *, version_id: uuid.UUID, user_id: uuid.UUID, limit: int = 10
    ) -> list[DocumentProcessingJob]:
        rows = await self._db.execute(
            select(DocumentProcessingJob)
            .where(
                DocumentProcessingJob.document_version_id == version_id,
                DocumentProcessingJob.user_id == user_id,
            )
            .order_by(DocumentProcessingJob.created_at.desc())
            .limit(limit)
        )
        return list(rows.scalars().all())
