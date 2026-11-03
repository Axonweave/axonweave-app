import uuid
from typing import Literal

from fastapi import APIRouter, Query

from app.core.dependencies import ActiveUser, DbSession
from app.modules.subjects.schemas import (
    CreateSubjectRequest,
    SubjectListResponse,
    SubjectOut,
    SubjectResponse,
    UpdateSubjectRequest,
)
from app.modules.subjects.service import SubjectService

router = APIRouter(tags=["subjects"])

_MAX_LIMIT = 100


@router.get("/workspaces/{workspace_id}/subjects", response_model=SubjectListResponse)
async def list_subjects(
    workspace_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
    include_archived: bool = Query(default=False),
    q: str | None = Query(default=None, max_length=255),
    sort_by: Literal["name", "updated_at"] = Query(default="name"),
    sort_dir: Literal["asc", "desc"] = Query(default="asc"),
    limit: int = Query(default=50, ge=1, le=_MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> SubjectListResponse:
    service = SubjectService(db)
    subjects, total = await service.list_subjects(
        workspace_id=workspace_id,
        user_id=current_user.id,
        include_archived=include_archived,
        q=q,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
    )
    return SubjectListResponse(
        data=[SubjectOut.model_validate(s) for s in subjects],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/workspaces/{workspace_id}/subjects", response_model=SubjectResponse, status_code=201)
async def create_subject(
    workspace_id: uuid.UUID,
    data: CreateSubjectRequest,
    current_user: ActiveUser,
    db: DbSession,
) -> SubjectResponse:
    service = SubjectService(db)
    subject = await service.create_subject(
        workspace_id=workspace_id,
        user_id=current_user.id,
        name=data.name,
        description=data.description,
        colour=data.colour,
        icon=data.icon,
    )
    return SubjectResponse(data=SubjectOut.model_validate(subject))


@router.get("/workspaces/{workspace_id}/subjects/{subject_id}", response_model=SubjectResponse)
async def get_subject(
    workspace_id: uuid.UUID,
    subject_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
) -> SubjectResponse:
    service = SubjectService(db)
    subject = await service.get_subject(
        subject_id=subject_id,
        workspace_id=workspace_id,
        user_id=current_user.id,
    )
    return SubjectResponse(data=SubjectOut.model_validate(subject))


@router.patch("/workspaces/{workspace_id}/subjects/{subject_id}", response_model=SubjectResponse)
async def update_subject(
    workspace_id: uuid.UUID,
    subject_id: uuid.UUID,
    data: UpdateSubjectRequest,
    current_user: ActiveUser,
    db: DbSession,
) -> SubjectResponse:
    service = SubjectService(db)
    subject = await service.update_subject(
        subject_id=subject_id,
        workspace_id=workspace_id,
        user_id=current_user.id,
        name=data.name,
        description=data.description,
        colour=data.colour,
        icon=data.icon,
    )
    return SubjectResponse(data=SubjectOut.model_validate(subject))


@router.delete("/workspaces/{workspace_id}/subjects/{subject_id}", status_code=204)
async def delete_subject(
    workspace_id: uuid.UUID,
    subject_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
) -> None:
    service = SubjectService(db)
    await service.delete_subject(
        subject_id=subject_id,
        workspace_id=workspace_id,
        user_id=current_user.id,
    )


@router.post(
    "/workspaces/{workspace_id}/subjects/{subject_id}/archive",
    response_model=SubjectResponse,
)
async def archive_subject(
    workspace_id: uuid.UUID,
    subject_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
) -> SubjectResponse:
    service = SubjectService(db)
    subject = await service.archive_subject(
        subject_id=subject_id,
        workspace_id=workspace_id,
        user_id=current_user.id,
    )
    return SubjectResponse(data=SubjectOut.model_validate(subject))


@router.post(
    "/workspaces/{workspace_id}/subjects/{subject_id}/restore",
    response_model=SubjectResponse,
)
async def restore_subject(
    workspace_id: uuid.UUID,
    subject_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
) -> SubjectResponse:
    service = SubjectService(db)
    subject = await service.restore_subject(
        subject_id=subject_id,
        workspace_id=workspace_id,
        user_id=current_user.id,
    )
    return SubjectResponse(data=SubjectOut.model_validate(subject))
