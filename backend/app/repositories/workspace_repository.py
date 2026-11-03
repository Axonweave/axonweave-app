"""Workspace repository — all DB operations for workspaces (scoped to owner)."""

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workspace import Workspace


class WorkspaceRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_for_user(self, workspace_id: uuid.UUID, user_id: uuid.UUID) -> Workspace | None:
        """Fetch one workspace — returns None (→ 404) if not owned by this user."""
        result = await self._db.execute(
            select(Workspace).where(
                Workspace.id == workspace_id,
                Workspace.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        name: str,
        workspace_type: str = "personal_learning",
        is_default: bool = False,
        description: str | None = None,
        icon: str | None = None,
        colour: str | None = None,
    ) -> Workspace:
        ws = Workspace(
            user_id=user_id,
            name=name,
            description=description,
            workspace_type=workspace_type,
            icon=icon,
            colour=colour,
            is_default=is_default,
        )
        self._db.add(ws)
        await self._db.flush()
        return ws

    async def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        include_archived: bool = False,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Workspace], int]:
        """Returns (rows, total). Always scoped to user_id."""
        q = select(Workspace).where(Workspace.user_id == user_id)
        if not include_archived:
            q = q.where(Workspace.archived_at.is_(None))
        q = q.order_by(Workspace.is_default.desc(), Workspace.updated_at.desc())

        count_q = select(func.count()).select_from(q.subquery())
        total_result = await self._db.execute(count_q)
        total = total_result.scalar_one()

        rows = await self._db.execute(q.limit(limit).offset(offset))
        return list(rows.scalars().all()), total

    async def name_exists(self, user_id: uuid.UUID, name: str, exclude_id: uuid.UUID | None = None) -> bool:
        """Case-insensitive name check among non-archived rows (D-11)."""
        q = select(Workspace.id).where(
            Workspace.user_id == user_id,
            func.lower(Workspace.name) == name.lower(),
            Workspace.archived_at.is_(None),
        )
        if exclude_id:
            q = q.where(Workspace.id != exclude_id)
        result = await self._db.execute(q)
        return result.scalar_one_or_none() is not None

    async def set_default(self, workspace: Workspace, user_id: uuid.UUID) -> None:
        """Clear any existing default and set this one (D-13)."""
        existing = await self._db.execute(
            select(Workspace).where(
                Workspace.user_id == user_id,
                Workspace.is_default.is_(True),
            )
        )
        for ws in existing.scalars().all():
            ws.is_default = False
        workspace.is_default = True
        await self._db.flush()

    async def archive(self, workspace: Workspace) -> None:
        workspace.archived_at = datetime.now(timezone.utc)
        await self._db.flush()

    async def restore(self, workspace: Workspace) -> None:
        workspace.archived_at = None
        await self._db.flush()

    async def delete(self, workspace: Workspace) -> None:
        await self._db.delete(workspace)
        await self._db.flush()
