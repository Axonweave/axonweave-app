"""Persistence for knowledge extraction jobs. User-facing reads are always scoped by `user_id`
(rule 3). The worker functions take only a job id from our own broker message. State changes are
guarded UPDATEs, so a duplicate delivery, a cancel and a stale sweep can never move a job out of a
terminal state (same discipline as `GenerationJobRepository`, D-85)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.knowledge import ACTIVE_JOB_STATUSES, KnowledgeExtractionJob
from app.models.subject import Subject
from app.models.workspace import Workspace

_RUNNING = tuple(s for s in ACTIVE_JOB_STATUSES if s != "pending")


def _rows(result: Any) -> int:
    return int(result.rowcount)


class KnowledgeJobRepository:
    # Paper analysis (Phase 7) runs the same job discipline on its own table: a subclass swaps the
    # model and the stored cancel code and inherits every guarded UPDATE.
    _m: Any = KnowledgeExtractionJob
    _cancel_code = "KNOWLEDGE_CANCELLED"

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # user-facing ─────────────────────────────────────────────────────────────

    async def add(self, **fields: Any) -> KnowledgeExtractionJob:
        job: KnowledgeExtractionJob = self._m(**fields)
        self._db.add(job)
        await self._db.flush()
        return job

    async def get_owned(
        self, job_id: uuid.UUID, user_id: uuid.UUID
    ) -> KnowledgeExtractionJob | None:
        return (
            await self._db.execute(
                select(self._m).where(self._m.id == job_id, self._m.user_id == user_id)
            )
        ).scalar_one_or_none()

    async def find_active_by_fingerprint(
        self, user_id: uuid.UUID, fingerprint: str
    ) -> KnowledgeExtractionJob | None:
        return (
            await self._db.execute(
                select(self._m).where(
                    self._m.user_id == user_id,
                    self._m.fingerprint == fingerprint,
                    self._m.status.in_(ACTIVE_JOB_STATUSES),
                )
            )
        ).scalar_one_or_none()

    async def count_active(self, user_id: uuid.UUID) -> int:
        return (
            await self._db.execute(
                select(func.count(self._m.id)).where(
                    self._m.user_id == user_id,
                    self._m.status.in_(ACTIVE_JOB_STATUSES),
                )
            )
        ).scalar_one()

    def _subject_documents(self, user_id: uuid.UUID, subject_id: uuid.UUID) -> Any:
        return select(Document.id).where(
            Document.user_id == user_id, Document.subject_id == subject_id
        )

    async def owned_subject(
        self, user_id: uuid.UUID, subject_id: uuid.UUID
    ) -> tuple[uuid.UUID, str] | None:
        """(workspace id, name) of a subject only if it belongs to this user, else None."""
        row = (
            await self._db.execute(
                select(Subject.workspace_id, Subject.name)
                .join(Workspace, Workspace.id == Subject.workspace_id)
                .where(Subject.id == subject_id, Workspace.user_id == user_id)
            )
        ).first()
        return None if row is None else (row[0], row[1])

    def _in_subject(self, user_id: uuid.UUID, subject_id: uuid.UUID) -> Any:
        """Document runs of the subject's documents, and web runs started for the subject."""
        return or_(
            self._m.document_id.in_(self._subject_documents(user_id, subject_id)),
            self._m.subject_id == subject_id,
        )

    async def count_active_for_subject(self, user_id: uuid.UUID, subject_id: uuid.UUID) -> int:
        return (
            await self._db.execute(
                select(func.count(self._m.id)).where(
                    self._m.user_id == user_id,
                    self._m.status.in_(ACTIVE_JOB_STATUSES),
                    self._in_subject(user_id, subject_id),
                )
            )
        ).scalar_one()

    async def delete_finished_for_subject(self, user_id: uuid.UUID, subject_id: uuid.UUID) -> int:
        """Forget finished runs for a subject so a cleared graph can be generated again (a
        completed job is what makes the subject run skip a document)."""
        result = await self._db.execute(
            delete(self._m).where(
                self._m.user_id == user_id,
                self._m.status.notin_(ACTIVE_JOB_STATUSES),
                self._in_subject(user_id, subject_id),
            )
        )
        return _rows(result)

    async def completed_document_ids(
        self, user_id: uuid.UUID, document_ids: Sequence[uuid.UUID], extraction_version: str
    ) -> set[uuid.UUID]:
        """Documents of this user that already have a completed extraction at this version."""
        if not document_ids:
            return set()
        rows = await self._db.execute(
            select(self._m.document_id)
            .where(
                self._m.user_id == user_id,
                self._m.document_id.in_(document_ids),
                self._m.status == "completed",
                self._m.extraction_version == extraction_version,
            )
            .distinct()
        )
        return set(rows.scalars())

    async def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        status: str | None,
        document_id: uuid.UUID | None,
        limit: int,
        offset: int,
        subject_id: uuid.UUID | None = None,
    ) -> tuple[list[KnowledgeExtractionJob], int]:
        conditions = [self._m.user_id == user_id]
        if status:
            conditions.append(self._m.status == status)
        if document_id:
            conditions.append(self._m.document_id == document_id)
        if subject_id:
            conditions.append(self._in_subject(user_id, subject_id))
        total = (
            await self._db.execute(select(func.count(self._m.id)).where(*conditions))
        ).scalar_one()
        rows = (
            await self._db.execute(
                select(self._m)
                .where(*conditions)
                .order_by(self._m.created_at.desc(), self._m.id.desc())
                .limit(limit)
                .offset(offset)
            )
        ).scalars()
        return list(rows), total

    async def request_cancel(self, job_id: uuid.UUID, user_id: uuid.UUID, now: datetime) -> str:
        """ "cancelled" (pending job, stopped at once), "requested" (running job gets a flag the
        worker checks between stages) or "finished"."""
        cancelled = await self._db.execute(
            update(self._m)
            .where(
                self._m.id == job_id,
                self._m.user_id == user_id,
                self._m.status == "pending",
            )
            .values(
                status="cancelled",
                cancel_requested=True,
                error_code=self._cancel_code,
                completed_at=now,
            )
        )
        if _rows(cancelled):
            return "cancelled"
        flagged = await self._db.execute(
            update(self._m)
            .where(
                self._m.id == job_id,
                self._m.user_id == user_id,
                self._m.status.in_(ACTIVE_JOB_STATUSES),
            )
            .values(cancel_requested=True)
        )
        return "requested" if _rows(flagged) else "finished"

    # worker ──────────────────────────────────────────────────────────────────

    async def get(self, job_id: uuid.UUID) -> KnowledgeExtractionJob | None:
        return (
            await self._db.execute(select(self._m).where(self._m.id == job_id))
        ).scalar_one_or_none()

    async def claim(self, job_id: uuid.UUID, now: datetime, task_id: str | None) -> bool:
        """pending -> retrieving_sources, exactly once. A redelivered or duplicate task finds the
        job already claimed and does nothing."""
        result = await self._db.execute(
            update(self._m)
            .where(
                self._m.id == job_id,
                self._m.status == "pending",
                self._m.cancel_requested.is_(False),
            )
            .values(
                status="retrieving_sources",
                progress=5,
                started_at=now,
                heartbeat_at=now,
                celery_task_id=task_id,
            )
        )
        return bool(_rows(result))

    async def set_stage(
        self, job_id: uuid.UUID, status: str, progress: int, now: datetime, **extra: Any
    ) -> bool:
        """Move an active job to the next stage. False when it is no longer active."""
        result = await self._db.execute(
            update(self._m)
            .where(self._m.id == job_id, self._m.status.in_(_RUNNING))
            .values(status=status, progress=progress, heartbeat_at=now, **extra)
        )
        return bool(_rows(result))

    async def update_active(self, job_id: uuid.UUID, now: datetime, **values: Any) -> bool:
        result = await self._db.execute(
            update(self._m)
            .where(self._m.id == job_id, self._m.status.in_(_RUNNING))
            .values(heartbeat_at=now, **values)
        )
        return bool(_rows(result))

    async def add_provider_call(self, job_id: uuid.UUID, now: datetime) -> None:
        await self._db.execute(
            update(self._m)
            .where(self._m.id == job_id)
            .values(provider_calls=self._m.provider_calls + 1, heartbeat_at=now)
        )

    async def is_cancel_requested(self, job_id: uuid.UUID) -> bool:
        flag = (
            await self._db.execute(select(self._m.cancel_requested).where(self._m.id == job_id))
        ).scalar_one_or_none()
        return bool(flag)

    async def finish(
        self,
        job_id: uuid.UUID,
        status: str,
        now: datetime,
        *,
        error_code: str | None = None,
        result_stats: dict[str, Any] | None = None,
        **extra: Any,
    ) -> bool:
        """Move an active job to a terminal state. False if it already finished (first wins)."""
        values: dict[str, Any] = {
            "status": status,
            "completed_at": now,
            "heartbeat_at": now,
            "error_code": error_code,
        }
        if status == "completed":
            values["progress"] = 100
        if result_stats is not None:
            values["result_stats"] = result_stats
        values.update(extra)
        result = await self._db.execute(
            update(self._m)
            .where(self._m.id == job_id, self._m.status.in_(_RUNNING))
            .values(**values)
        )
        return bool(_rows(result))

    async def pending_older_than(self, cutoff: datetime, limit: int) -> list[uuid.UUID]:
        rows = await self._db.execute(
            select(self._m.id)
            .where(
                self._m.status == "pending",
                self._m.cancel_requested.is_(False),
                self._m.created_at < cutoff,
                (self._m.heartbeat_at.is_(None)) | (self._m.heartbeat_at < cutoff),
            )
            .order_by(self._m.created_at)
            .limit(limit)
        )
        return list(rows.scalars())

    async def touch(self, job_id: uuid.UUID, now: datetime) -> None:
        await self._db.execute(update(self._m).where(self._m.id == job_id).values(heartbeat_at=now))

    async def fail_stale(self, cutoff: datetime, now: datetime, error_code: str) -> int:
        """Jobs that started but stopped reporting (worker killed). Failed, never restarted: the
        provider may already have run and been billed."""
        result = await self._db.execute(
            update(self._m)
            .where(
                self._m.status.in_(_RUNNING),
                self._m.heartbeat_at < cutoff,
            )
            .values(status="failed", error_code=error_code, completed_at=now)
        )
        return _rows(result)
