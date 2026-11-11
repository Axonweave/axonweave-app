"""Persistence for study exports. Every client-facing read is scoped by `user_id`."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.study_export import StudyExport
from app.models.study_material import StudyMaterial


class StudyExportRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def add(
        self, user_id: uuid.UUID, material_id: uuid.UUID, export_format: str
    ) -> StudyExport:
        row = StudyExport(
            user_id=user_id,
            study_material_id=material_id,
            export_format=export_format,
            status="pending",
        )
        self._db.add(row)
        await self._db.flush()
        return row

    async def get_owned(self, export_id: uuid.UUID, user_id: uuid.UUID) -> StudyExport | None:
        return (
            await self._db.execute(
                select(StudyExport).where(
                    StudyExport.id == export_id, StudyExport.user_id == user_id
                )
            )
        ).scalar_one_or_none()

    async def get(self, export_id: uuid.UUID) -> StudyExport | None:
        """Worker-side load: the id came from our own queue, never from a client."""
        return (
            await self._db.execute(select(StudyExport).where(StudyExport.id == export_id))
        ).scalar_one_or_none()

    async def keys_for_material(self, material_id: uuid.UUID, user_id: uuid.UUID) -> list[str]:
        rows = await self._db.execute(
            select(StudyExport.storage_key).where(
                StudyExport.study_material_id == material_id,
                StudyExport.user_id == user_id,
                StudyExport.storage_key.is_not(None),
            )
        )
        return [k for k in rows.scalars() if k]

    async def keys_for_user(self, user_id: uuid.UUID) -> list[str]:
        rows = await self._db.execute(
            select(StudyExport.storage_key).where(
                StudyExport.user_id == user_id, StudyExport.storage_key.is_not(None)
            )
        )
        return [k for k in rows.scalars() if k]

    async def keys_for_workspace(self, workspace_id: uuid.UUID) -> list[str]:
        rows = await self._db.execute(
            select(StudyExport.storage_key)
            .join(StudyMaterial, StudyMaterial.id == StudyExport.study_material_id)
            .where(StudyMaterial.workspace_id == workspace_id, StudyExport.storage_key.is_not(None))
        )
        return [k for k in rows.scalars() if k]

    async def pending_older_than(self, cutoff: datetime, limit: int) -> list[uuid.UUID]:
        rows = await self._db.execute(
            select(StudyExport.id)
            .where(StudyExport.status == "pending", StudyExport.created_at < cutoff)
            .limit(limit)
        )
        return list(rows.scalars())

    async def due_for_expiry(self, now: datetime, limit: int) -> list[StudyExport]:
        rows = await self._db.execute(
            select(StudyExport)
            .where(
                StudyExport.status == "completed",
                StudyExport.expires_at.is_not(None),
                StudyExport.expires_at <= now,
            )
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list(rows.scalars())

    async def recent_count(self, user_id: uuid.UUID, since: datetime) -> int:
        return int(
            (
                await self._db.execute(
                    select(func.count())
                    .select_from(StudyExport)
                    .where(StudyExport.user_id == user_id, StudyExport.created_at >= since)
                )
            ).scalar_one()
        )

    async def mark_failed(self, export_id: uuid.UUID, code: str) -> None:
        await self._db.execute(
            update(StudyExport)
            .where(StudyExport.id == export_id)
            .values(status="failed", error_code=code)
        )
