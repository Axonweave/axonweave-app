import uuid

from fastapi import APIRouter, Query

from app.core.dependencies import ActiveUser, DbSession
from app.modules.folders.schemas import (
    CreateFolderRequest,
    FolderListResponse,
    FolderOut,
    FolderResponse,
    UpdateFolderRequest,
)
from app.modules.folders.service import FolderService

router = APIRouter(tags=["folders"])


@router.get(
    "/workspaces/{workspace_id}/subjects/{subject_id}/folders", response_model=FolderListResponse
)
async def list_folders(
    workspace_id: uuid.UUID,
    subject_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
    parent_folder_id: uuid.UUID | None = Query(default=None),
    include_archived: bool = Query(default=False),
    all_levels: bool = Query(default=False),
) -> FolderListResponse:
    service = FolderService(db)
    folders = await service.list_folders(
        workspace_id=workspace_id,
        subject_id=subject_id,
        user_id=current_user.id,
        parent_folder_id=parent_folder_id,
        include_archived=include_archived,
        all_levels=all_levels,
    )
    return FolderListResponse(data=[FolderOut.model_validate(f) for f in folders])


@router.post(
    "/workspaces/{workspace_id}/subjects/{subject_id}/folders",
    response_model=FolderResponse,
    status_code=201,
)
async def create_folder(
    workspace_id: uuid.UUID,
    subject_id: uuid.UUID,
    data: CreateFolderRequest,
    current_user: ActiveUser,
    db: DbSession,
) -> FolderResponse:
    service = FolderService(db)
    folder = await service.create_folder(
        workspace_id=workspace_id,
        subject_id=subject_id,
        user_id=current_user.id,
        name=data.name,
        parent_folder_id=data.parent_folder_id,
        description=data.description,
        display_order=data.display_order,
    )
    return FolderResponse(data=FolderOut.model_validate(folder))


@router.get(
    "/workspaces/{workspace_id}/subjects/{subject_id}/folders/{folder_id}",
    response_model=FolderResponse,
)
async def get_folder(
    workspace_id: uuid.UUID,
    subject_id: uuid.UUID,
    folder_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
) -> FolderResponse:
    service = FolderService(db)
    folder = await service.get_folder(
        folder_id=folder_id,
        subject_id=subject_id,
        workspace_id=workspace_id,
        user_id=current_user.id,
    )
    return FolderResponse(data=FolderOut.model_validate(folder))


@router.patch(
    "/workspaces/{workspace_id}/subjects/{subject_id}/folders/{folder_id}",
    response_model=FolderResponse,
)
async def update_folder(
    workspace_id: uuid.UUID,
    subject_id: uuid.UUID,
    folder_id: uuid.UUID,
    data: UpdateFolderRequest,
    current_user: ActiveUser,
    db: DbSession,
) -> FolderResponse:
    service = FolderService(db)
    folder = await service.update_folder(
        folder_id=folder_id,
        subject_id=subject_id,
        workspace_id=workspace_id,
        user_id=current_user.id,
        name=data.name,
        description=data.description,
        display_order=data.display_order,
        parent_folder_id=data.parent_folder_id,
        parent_folder_id_set=data.parent_folder_id_set,
    )
    return FolderResponse(data=FolderOut.model_validate(folder))


@router.delete(
    "/workspaces/{workspace_id}/subjects/{subject_id}/folders/{folder_id}",
    status_code=204,
)
async def delete_folder(
    workspace_id: uuid.UUID,
    subject_id: uuid.UUID,
    folder_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
    cascade: bool = Query(default=False),
) -> None:
    service = FolderService(db)
    await service.delete_folder(
        folder_id=folder_id,
        subject_id=subject_id,
        workspace_id=workspace_id,
        user_id=current_user.id,
        cascade=cascade,
    )


@router.post(
    "/workspaces/{workspace_id}/subjects/{subject_id}/folders/{folder_id}/archive",
    response_model=FolderResponse,
)
async def archive_folder(
    workspace_id: uuid.UUID,
    subject_id: uuid.UUID,
    folder_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
) -> FolderResponse:
    service = FolderService(db)
    folder = await service.archive_folder(
        folder_id=folder_id,
        subject_id=subject_id,
        workspace_id=workspace_id,
        user_id=current_user.id,
    )
    return FolderResponse(data=FolderOut.model_validate(folder))


@router.post(
    "/workspaces/{workspace_id}/subjects/{subject_id}/folders/{folder_id}/restore",
    response_model=FolderResponse,
)
async def restore_folder(
    workspace_id: uuid.UUID,
    subject_id: uuid.UUID,
    folder_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
) -> FolderResponse:
    service = FolderService(db)
    folder = await service.restore_folder(
        folder_id=folder_id,
        subject_id=subject_id,
        workspace_id=workspace_id,
        user_id=current_user.id,
    )
    return FolderResponse(data=FolderOut.model_validate(folder))
