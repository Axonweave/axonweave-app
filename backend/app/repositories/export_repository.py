"""Owner-scoped reads for the user data export (D-24); each joins up to workspaces.user_id."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_log import ActivityLog
from app.models.chapter import Chapter
from app.models.folder import Folder
from app.models.subject import Subject
from app.models.workspace import Workspace


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


class ExportRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def workspaces(self, user_id: uuid.UUID) -> list[dict[str, Any]]:
        rows = (
            (
                await self._db.execute(
                    select(Workspace).where(Workspace.user_id == user_id).order_by(Workspace.name)
                )
            )
            .scalars()
            .all()
        )
        return [
            {
                "id": str(w.id),
                "name": w.name,
                "description": w.description,
                "workspace_type": w.workspace_type,
                "is_default": w.is_default,
                "archived_at": _iso(w.archived_at),
                "created_at": _iso(w.created_at),
                "updated_at": _iso(w.updated_at),
            }
            for w in rows
        ]

    async def subjects(self, user_id: uuid.UUID) -> list[dict[str, Any]]:
        rows = (
            (
                await self._db.execute(
                    select(Subject)
                    .join(Workspace, Subject.workspace_id == Workspace.id)
                    .where(Workspace.user_id == user_id)
                    .order_by(Subject.name)
                )
            )
            .scalars()
            .all()
        )
        return [
            {
                "id": str(s.id),
                "workspace_id": str(s.workspace_id),
                "name": s.name,
                "description": s.description,
                "archived_at": _iso(s.archived_at),
                "created_at": _iso(s.created_at),
                "updated_at": _iso(s.updated_at),
            }
            for s in rows
        ]

    async def folders(self, user_id: uuid.UUID) -> list[dict[str, Any]]:
        rows = (
            (
                await self._db.execute(
                    select(Folder)
                    .join(Subject, Folder.subject_id == Subject.id)
                    .join(Workspace, Subject.workspace_id == Workspace.id)
                    .where(Workspace.user_id == user_id)
                    .order_by(Folder.name)
                )
            )
            .scalars()
            .all()
        )
        return [
            {
                "id": str(f.id),
                "subject_id": str(f.subject_id),
                "parent_folder_id": str(f.parent_folder_id) if f.parent_folder_id else None,
                "name": f.name,
                "description": f.description,
                "archived_at": _iso(f.archived_at),
                "created_at": _iso(f.created_at),
                "updated_at": _iso(f.updated_at),
            }
            for f in rows
        ]

    async def chapters(self, user_id: uuid.UUID) -> list[dict[str, Any]]:
        rows = (
            (
                await self._db.execute(
                    select(Chapter)
                    .join(Subject, Chapter.subject_id == Subject.id)
                    .join(Workspace, Subject.workspace_id == Workspace.id)
                    .where(Workspace.user_id == user_id)
                    .order_by(Chapter.title)
                )
            )
            .scalars()
            .all()
        )
        return [
            {
                "id": str(c.id),
                "subject_id": str(c.subject_id),
                "folder_id": str(c.folder_id) if c.folder_id else None,
                "title": c.title,
                "description": c.description,
                "status": c.status,
                "display_order": c.display_order,
                "archived_at": _iso(c.archived_at),
                "created_at": _iso(c.created_at),
                "updated_at": _iso(c.updated_at),
            }
            for c in rows
        ]

    async def activity(self, user_id: uuid.UUID) -> list[dict[str, Any]]:
        rows = (
            (
                await self._db.execute(
                    select(ActivityLog)
                    .where(ActivityLog.user_id == user_id)
                    .order_by(ActivityLog.created_at.desc())
                )
            )
            .scalars()
            .all()
        )
        return [
            {
                "action": a.action,
                "entity_type": a.entity_type,
                "entity_name": a.entity_name,
                "created_at": _iso(a.created_at),
            }
            for a in rows
        ]
