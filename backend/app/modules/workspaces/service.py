"""Workspaces service (B2)."""

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.user import User
from app.models.workspace import Workspace
from app.modules.workspaces.schemas import CreateWorkspaceRequest, UpdateWorkspaceRequest
from app.repositories.activity_repository import ActivityRepository
from app.repositories.workspace_repository import WorkspaceRepository

logger = get_logger(__name__)


class WorkspacesService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._activity = ActivityRepository(db)
        self._repo = WorkspaceRepository(db)

    async def list_workspaces(
        self, user: User, *, include_archived: bool = False, limit: int = 20, offset: int = 0
    ) -> tuple[list[Workspace], int]:
        return await self._repo.list_for_user(
            user.id, include_archived=include_archived, limit=limit, offset=offset
        )

    async def get_workspace(self, workspace_id: uuid.UUID, user: User) -> Workspace:
        ws = await self._repo.get_for_user(workspace_id, user.id)
        if ws is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "WORKSPACE_NOT_FOUND", "message": "Workspace not found."},
            )
        return ws

    async def create_workspace(self, user: User, data: CreateWorkspaceRequest) -> Workspace:
        if await self._repo.name_exists(user.id, data.name):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "WORKSPACE_NAME_CONFLICT",
                    "message": "A workspace with this name already exists.",
                },
            )
        ws = await self._repo.create(
            user_id=user.id,
            name=data.name,
            description=data.description,
            workspace_type=data.workspace_type,
            icon=data.icon,
            colour=data.colour,
        )
        await self._activity.record(
            user_id=user.id,
            action="created",
            entity_type="workspace",
            entity_id=ws.id,
            entity_name=ws.name,
            workspace_id=ws.id,
        )
        logger.info("workspace_created", user_id=str(user.id), workspace_id=str(ws.id))
        return ws

    async def update_workspace(
        self, workspace_id: uuid.UUID, user: User, data: UpdateWorkspaceRequest
    ) -> Workspace:
        ws = await self.get_workspace(workspace_id, user)
        if data.name is not None and data.name.lower() != ws.name.lower():
            if await self._repo.name_exists(user.id, data.name, exclude_id=ws.id):
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "WORKSPACE_NAME_CONFLICT",
                        "message": "A workspace with this name already exists.",
                    },
                )
            ws.name = data.name
        if data.description is not None:
            ws.description = data.description
        if data.workspace_type is not None:
            ws.workspace_type = data.workspace_type
        if data.icon is not None:
            ws.icon = data.icon
        if data.colour is not None:
            ws.colour = data.colour
        ws.updated_at = datetime.now(UTC)
        await self._db.flush()
        await self._activity.record(
            user_id=user.id,
            action="updated",
            entity_type="workspace",
            entity_id=ws.id,
            entity_name=ws.name,
            workspace_id=ws.id,
        )
        return ws

    async def set_default(self, workspace_id: uuid.UUID, user: User) -> Workspace:
        ws = await self.get_workspace(workspace_id, user)
        await self._repo.set_default(ws, user.id)
        return ws

    async def archive_workspace(self, workspace_id: uuid.UUID, user: User) -> Workspace:
        ws = await self.get_workspace(workspace_id, user)
        if ws.is_default:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "CANNOT_ARCHIVE_DEFAULT",
                    "message": "Cannot archive the default workspace. Set another default first.",
                },
            )
        await self._repo.archive(ws)
        await self._activity.record(
            user_id=user.id,
            action="archived",
            entity_type="workspace",
            entity_id=ws.id,
            entity_name=ws.name,
            workspace_id=ws.id,
        )
        return ws

    async def restore_workspace(self, workspace_id: uuid.UUID, user: User) -> Workspace:
        ws = await self._repo.get_for_user(workspace_id, user.id)
        if ws is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "WORKSPACE_NOT_FOUND", "message": "Workspace not found."},
            )
        if ws.archived_at is None:
            raise HTTPException(
                status_code=409,
                detail={"code": "NOT_ARCHIVED", "message": "Workspace is not archived."},
            )
        # Check new name won't conflict
        if await self._repo.name_exists(user.id, ws.name):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "WORKSPACE_NAME_CONFLICT",
                    "message": "A workspace with this name already exists. Rename it first.",
                },
            )
        await self._repo.restore(ws)
        await self._activity.record(
            user_id=user.id,
            action="restored",
            entity_type="workspace",
            entity_id=ws.id,
            entity_name=ws.name,
            workspace_id=ws.id,
        )
        return ws

    async def delete_workspace(self, workspace_id: uuid.UUID, user: User) -> None:
        ws = await self.get_workspace(workspace_id, user)
        if ws.is_default:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "CANNOT_DELETE_DEFAULT",
                    "message": "Cannot delete the default workspace. Set another as default first.",
                },
            )
        await self._activity.record(
            user_id=user.id,
            action="deleted",
            entity_type="workspace",
            entity_id=ws.id,
            entity_name=ws.name,
            workspace_id=None,
        )
        await self._repo.delete(ws)
        logger.info("workspace_deleted", user_id=str(user.id), workspace_id=str(workspace_id))
