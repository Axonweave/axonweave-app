"""Workspaces routes (B2)."""

import uuid

from fastapi import APIRouter, Query

from app.core.dependencies import ActiveUser, DbSession
from app.modules.workspaces.schemas import (
    CreateWorkspaceRequest,
    UpdateWorkspaceRequest,
    WorkspaceListResponse,
    WorkspaceOut,
    WorkspaceResponse,
)
from app.modules.workspaces.service import WorkspacesService

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.get("", response_model=WorkspaceListResponse)
async def list_workspaces(
    current_user: ActiveUser,
    db: DbSession,
    include_archived: bool = Query(False),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> WorkspaceListResponse:
    service = WorkspacesService(db)
    workspaces, total = await service.list_workspaces(
        current_user, include_archived=include_archived, limit=limit, offset=offset
    )
    return WorkspaceListResponse(
        data=[WorkspaceOut.model_validate(w) for w in workspaces], total=total
    )


@router.post("", response_model=WorkspaceResponse, status_code=201)
async def create_workspace(
    data: CreateWorkspaceRequest,
    current_user: ActiveUser,
    db: DbSession,
) -> WorkspaceResponse:
    service = WorkspacesService(db)
    ws = await service.create_workspace(current_user, data)
    return WorkspaceResponse(data=WorkspaceOut.model_validate(ws))


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
) -> WorkspaceResponse:
    service = WorkspacesService(db)
    ws = await service.get_workspace(workspace_id, current_user)
    return WorkspaceResponse(data=WorkspaceOut.model_validate(ws))


@router.patch("/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    workspace_id: uuid.UUID,
    data: UpdateWorkspaceRequest,
    current_user: ActiveUser,
    db: DbSession,
) -> WorkspaceResponse:
    service = WorkspacesService(db)
    ws = await service.update_workspace(workspace_id, current_user, data)
    return WorkspaceResponse(data=WorkspaceOut.model_validate(ws))


@router.post("/{workspace_id}/set-default", response_model=WorkspaceResponse)
async def set_default(
    workspace_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
) -> WorkspaceResponse:
    service = WorkspacesService(db)
    ws = await service.set_default(workspace_id, current_user)
    return WorkspaceResponse(data=WorkspaceOut.model_validate(ws))


@router.post("/{workspace_id}/archive", response_model=WorkspaceResponse)
async def archive_workspace(
    workspace_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
) -> WorkspaceResponse:
    service = WorkspacesService(db)
    ws = await service.archive_workspace(workspace_id, current_user)
    return WorkspaceResponse(data=WorkspaceOut.model_validate(ws))


@router.post("/{workspace_id}/restore", response_model=WorkspaceResponse)
async def restore_workspace(
    workspace_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
) -> WorkspaceResponse:
    service = WorkspacesService(db)
    ws = await service.restore_workspace(workspace_id, current_user)
    return WorkspaceResponse(data=WorkspaceOut.model_validate(ws))


@router.delete("/{workspace_id}", status_code=200)
async def delete_workspace(
    workspace_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
) -> dict[str, object]:
    service = WorkspacesService(db)
    await service.delete_workspace(workspace_id, current_user)
    return {"success": True, "data": None}
