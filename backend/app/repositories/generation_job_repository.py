"""Persistence for generation jobs. User-facing reads are always scoped by `user_id` (rule 3). The
worker functions take only a job id that came from our own broker message; they never accept ids
from a request. State changes are guarded UPDATEs, so a duplicate Celery delivery, a cancel and a
stale-job sweep can never move a job out of a terminal state."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.generation_job import ACTIVE_STATUSES, GenerationJob

TERMINAL = ("completed", "failed", "cancelled")
_RUNNING = tuple(s for s in ACTIVE_STATUSES if s != "pending")


def _rows(result: Any) -> int:
    return int(result.rowcount)


class GenerationJobRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # user-facing ─────────────────────────────────────────────────────────────

    async def add(self, **fields: Any) -> GenerationJob:
        job = GenerationJob(**fields)
        self._db.add(job)
        await self._db.flush()
        return job

    async def get_owned(self, job_id: uuid.UUID, user_id: uuid.UUID) -> GenerationJob | None:
        return (
            await self._db.execute(
                select(GenerationJob).where(
                    GenerationJob.id == job_id, GenerationJob.user_id == user_id
                )
            )
        ).scalar_one_or_none()

    async def find_active_by_fingerprint(
        self, user_id: uuid.UUID, fingerprint: str
    ) -> GenerationJob | None:
        return (
            await self._db.execute(
                select(GenerationJob).where(
                    GenerationJob.user_id == user_id,
                    GenerationJob.fingerprint == fingerprint,
                    GenerationJob.status.in_(ACTIVE_STATUSES),
                )
            )
        ).scalar_one_or_none()

    async def count_active(self, user_id: uuid.UUID) -> int:
        return (
            await self._db.execute(
                select(func.count(GenerationJob.id)).where(
                    GenerationJob.user_id == user_id, GenerationJob.status.in_(ACTIVE_STATUSES)
                )
            )
        ).scalar_one()

    async def count_since(self, user_id: uuid.UUID, since: datetime) -> int:
        """Jobs that count against the daily quota: every job created since `since` except those
        that ended without ever reaching the provider (nothing was spent)."""
        return (
            await self._db.execute(
                select(func.count(GenerationJob.id)).where(
                    GenerationJob.user_id == user_id,
                    GenerationJob.created_at >= since,
                    ~(
                        GenerationJob.status.in_(("failed", "cancelled"))
                        & (GenerationJob.provider_calls == 0)
                    ),
                )
            )
        ).scalar_one()

    async def list_for_user(
        self, user_id: uuid.UUID, *, status: str | None, limit: int, offset: int
    ) -> tuple[list[GenerationJob], int]:
        conditions = [GenerationJob.user_id == user_id]
        if status:
            conditions.append(GenerationJob.status == status)
        total = (
            await self._db.execute(select(func.count(GenerationJob.id)).where(*conditions))
        ).scalar_one()
        rows = (
            await self._db.execute(
                select(GenerationJob)
                .where(*conditions)
                .order_by(GenerationJob.created_at.desc(), GenerationJob.id.desc())
                .limit(limit)
                .offset(offset)
            )
        ).scalars()
        return list(rows), total

    async def request_cancel(self, job_id: uuid.UUID, user_id: uuid.UUID, now: datetime) -> str:
        """Cancel a job the user owns. A pending job (not picked up yet) is cancelled at once; a
        running one gets a flag the worker checks between stages and while waiting on the provider.
        Returns "cancelled", "requested" or "finished"."""
        cancelled = await self._db.execute(
            update(GenerationJob)
            .where(
                GenerationJob.id == job_id,
                GenerationJob.user_id == user_id,
                GenerationJob.status == "pending",
            )
            .values(
                status="cancelled",
                cancel_requested=True,
                error_code="GENERATION_CANCELLED",
                completed_at=now,
            )
        )
        if _rows(cancelled):
            return "cancelled"
        flagged = await self._db.execute(
            update(GenerationJob)
            .where(
                GenerationJob.id == job_id,
                GenerationJob.user_id == user_id,
                GenerationJob.status.in_(ACTIVE_STATUSES),
            )
            .values(cancel_requested=True)
        )
        return "requested" if _rows(flagged) else "finished"

    # worker ──────────────────────────────────────────────────────────────────

    async def get(self, job_id: uuid.UUID) -> GenerationJob | None:
        return (
            await self._db.execute(select(GenerationJob).where(GenerationJob.id == job_id))
        ).scalar_one_or_none()

    async def claim(self, job_id: uuid.UUID, now: datetime, task_id: str | None) -> bool:
        """pending -> retrieving_sources, exactly once. A redelivered or duplicate task finds the
        job already claimed and does nothing: an expensive run is never restarted (D-88)."""
        result = await self._db.execute(
            update(GenerationJob)
            .where(
                GenerationJob.id == job_id,
                GenerationJob.status == "pending",
                GenerationJob.cancel_requested.is_(False),
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
            update(GenerationJob)
            .where(GenerationJob.id == job_id, GenerationJob.status.in_(_RUNNING))
            .values(status=status, progress=progress, heartbeat_at=now, **extra)
        )
        return bool(_rows(result))

    async def update_active(self, job_id: uuid.UUID, now: datetime, **values: Any) -> bool:
        result = await self._db.execute(
            update(GenerationJob)
            .where(GenerationJob.id == job_id, GenerationJob.status.in_(_RUNNING))
            .values(heartbeat_at=now, **values)
        )
        return bool(_rows(result))

    async def add_provider_call(self, job_id: uuid.UUID, now: datetime) -> None:
        await self._db.execute(
            update(GenerationJob)
            .where(GenerationJob.id == job_id)
            .values(provider_calls=GenerationJob.provider_calls + 1, heartbeat_at=now)
        )

    async def is_cancel_requested(self, job_id: uuid.UUID) -> bool:
        flag = (
            await self._db.execute(
                select(GenerationJob.cancel_requested).where(GenerationJob.id == job_id)
            )
        ).scalar_one_or_none()
        return bool(flag)

    async def finish(
        self,
        job_id: uuid.UUID,
        status: str,
        now: datetime,
        *,
        error_code: str | None = None,
        material_id: uuid.UUID | None = None,
        preview: dict[str, Any] | None = None,
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
            values["study_material_id"] = material_id
            if preview is not None:
                values["preview"] = preview
        result = await self._db.execute(
            update(GenerationJob)
            .where(GenerationJob.id == job_id, GenerationJob.status.in_(_RUNNING))
            .values(**values)
        )
        return bool(_rows(result))

    async def pending_older_than(self, cutoff: datetime, limit: int) -> list[uuid.UUID]:
        rows = await self._db.execute(
            select(GenerationJob.id)
            .where(
                GenerationJob.status == "pending",
                GenerationJob.cancel_requested.is_(False),
                GenerationJob.created_at < cutoff,
                (GenerationJob.heartbeat_at.is_(None)) | (GenerationJob.heartbeat_at < cutoff),
            )
            .order_by(GenerationJob.created_at)
            .limit(limit)
        )
        return list(rows.scalars())

    async def touch(self, job_id: uuid.UUID, now: datetime) -> None:
        await self._db.execute(
            update(GenerationJob).where(GenerationJob.id == job_id).values(heartbeat_at=now)
        )

    async def fail_stale(self, cutoff: datetime, now: datetime, error_code: str) -> int:
        """Jobs that started but stopped reporting (worker killed). They are failed, never
        restarted: the provider may already have run and been billed (D-88)."""
        result = await self._db.execute(
            update(GenerationJob)
            .where(GenerationJob.status.in_(_RUNNING), GenerationJob.heartbeat_at < cutoff)
            .values(status="failed", error_code=error_code, completed_at=now)
        )
        return _rows(result)
