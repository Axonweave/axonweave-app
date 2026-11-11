"""Export service (spec 14, 19.5, D-100): create, status, download. The file is rendered by the
worker; the download is streamed from private storage after an ownership and expiry check."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.study_export import StudyExport
from app.models.user import User
from app.repositories.study_export_repository import StudyExportRepository
from app.repositories.study_material_repository import StudyMaterialRepository
from app.storage.base import StorageBackend, StorageError
from app.study.dispatch import ExportDispatcher
from app.study.errors import (
    ExportExpiredError,
    ExportFormatError,
    ExportNotFoundError,
    ExportNotReadyError,
    ExportRateLimitedError,
    ExportUnavailableError,
    MaterialNotFoundError,
)
from app.study.exporting import FORMATS_BY_TYPE


def effective_status(row: StudyExport) -> str:
    """`completed` past its expiry reads as `expired` immediately; the sweeper deletes the file."""
    if row.status == "completed" and row.expires_at and row.expires_at <= datetime.now(UTC):
        return "expired"
    return row.status


class StudyExportService:
    def __init__(self, db: AsyncSession, settings: Settings, dispatcher: ExportDispatcher) -> None:
        self._db = db
        self._s = settings
        self._dispatcher = dispatcher
        self._exports = StudyExportRepository(db)

    async def create(self, user: User, material_id: uuid.UUID, fmt: str) -> StudyExport:
        user_id = user.id  # read before commit expires the loaded user
        material = await StudyMaterialRepository(self._db).get_owned(material_id, user_id)
        if material is None:
            raise MaterialNotFoundError  # foreign and missing look the same
        if material.status != "completed" or fmt not in FORMATS_BY_TYPE.get(
            material.resource_type, ()
        ):
            raise ExportFormatError
        if not self._dispatcher.available():
            raise ExportUnavailableError
        since = datetime.now(UTC) - timedelta(hours=1)
        if (
            await self._exports.recent_count(user_id, since)
            >= self._s.study_exports_per_hour_per_user
        ):
            raise ExportRateLimitedError(retry_after=3600)
        row = await self._exports.add(user_id, material.id, fmt)
        export_id = row.id
        await self._db.commit()
        self._dispatcher.dispatch(export_id)  # if refused it stays pending; the sweeper resends
        await self._db.refresh(row)
        return row

    async def get(self, user: User, export_id: uuid.UUID) -> StudyExport:
        row = await self._exports.get_owned(export_id, user.id)
        if row is None:
            raise ExportNotFoundError
        return row

    async def download(
        self, user: User, export_id: uuid.UUID, storage: StorageBackend
    ) -> tuple[StudyExport, AsyncIterator[bytes]]:
        row = await self.get(user, export_id)
        if effective_status(row) == "expired":
            raise ExportExpiredError
        if row.status != "completed" or not row.storage_key:
            raise ExportNotReadyError
        try:
            if not await storage.exists(row.storage_key):
                raise ExportExpiredError
        except StorageError:
            raise ExportUnavailableError from None
        return row, storage.open(row.storage_key)
