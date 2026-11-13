"""Research Studio routes (Phase 7). Milestone 7.1: research projects. Every route needs an active
session; writes are covered by the app's CSRF protection (D-04)."""

import uuid

from fastapi import APIRouter, Query

from app.core.dependencies import ActiveUser, DbSession
from app.modules.research.schemas import (
    ProjectCreate,
    ProjectListResponse,
    ProjectOut,
    ProjectPatch,
    ProjectResponse,
    SortLiteral,
    StatusLiteral,
)
from app.modules.research.service import ResearchProjectService

router = APIRouter(prefix="/research", tags=["research"])


@router.get("/projects", response_model=ProjectListResponse)
async def list_projects(
    current_user: ActiveUser,
    db: DbSession,
    workspace_id: uuid.UUID | None = None,
    status: StatusLiteral | None = None,
    q: str | None = Query(None, max_length=100),
    archived: bool = False,
    sort_by: SortLiteral = "updated_at",
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> ProjectListResponse:
    rows, total = await ResearchProjectService(db).list(
        current_user.id,
        workspace_id=workspace_id,
        status=status,
        q=q,
        archived=archived,
        sort_by=sort_by,
        descending=sort_dir == "desc",
        limit=limit,
        offset=offset,
    )
    return ProjectListResponse(
        data=[ProjectOut.model_validate(r) for r in rows], total=total, limit=limit, offset=offset
    )


@router.post("/projects", response_model=ProjectResponse, status_code=201)
async def create_project(
    body: ProjectCreate, current_user: ActiveUser, db: DbSession
) -> ProjectResponse:
    project = await ResearchProjectService(db).create(current_user.id, body)
    return ProjectResponse(data=ProjectOut.model_validate(project))


@router.get("/projects/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: uuid.UUID, current_user: ActiveUser, db: DbSession
) -> ProjectResponse:
    project = await ResearchProjectService(db).get(current_user.id, project_id)
    return ProjectResponse(data=ProjectOut.model_validate(project))


@router.patch("/projects/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: uuid.UUID, body: ProjectPatch, current_user: ActiveUser, db: DbSession
) -> ProjectResponse:
    project = await ResearchProjectService(db).update(current_user.id, project_id, body)
    return ProjectResponse(data=ProjectOut.model_validate(project))


@router.post("/projects/{project_id}/archive", response_model=ProjectResponse)
async def archive_project(
    project_id: uuid.UUID, current_user: ActiveUser, db: DbSession
) -> ProjectResponse:
    project = await ResearchProjectService(db).archive(current_user.id, project_id)
    return ProjectResponse(data=ProjectOut.model_validate(project))


@router.post("/projects/{project_id}/restore", response_model=ProjectResponse)
async def restore_project(
    project_id: uuid.UUID, current_user: ActiveUser, db: DbSession
) -> ProjectResponse:
    project = await ResearchProjectService(db).restore(current_user.id, project_id)
    return ProjectResponse(data=ProjectOut.model_validate(project))


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(project_id: uuid.UUID, current_user: ActiveUser, db: DbSession) -> None:
    await ResearchProjectService(db).delete(current_user.id, project_id)
