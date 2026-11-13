"""Research Studio routes (Phase 7). Milestone 7.1: research projects. Every route needs an active
session; writes are covered by the app's CSRF protection (D-04)."""

import uuid

from fastapi import APIRouter, Query

from app.core.dependencies import ActiveUser, DbSession
from app.models.research import ResearchProject
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
from app.repositories.research_paper_repository import ResearchPaperRepository

router = APIRouter(prefix="/research", tags=["research"])


async def _outs(db: DbSession, user_id: uuid.UUID, rows: list[ResearchProject]) -> list[ProjectOut]:
    counts = await ResearchPaperRepository(db).counts_by_project(user_id, [r.id for r in rows])
    out = []
    for r in rows:
        item = ProjectOut.model_validate(r)
        item.paper_count = counts.get(r.id, 0)
        out.append(item)
    return out


async def _out(db: DbSession, user_id: uuid.UUID, project: ResearchProject) -> ProjectOut:
    return (await _outs(db, user_id, [project]))[0]


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
        data=await _outs(db, current_user.id, rows), total=total, limit=limit, offset=offset
    )


@router.post("/projects", response_model=ProjectResponse, status_code=201)
async def create_project(
    body: ProjectCreate, current_user: ActiveUser, db: DbSession
) -> ProjectResponse:
    project = await ResearchProjectService(db).create(current_user.id, body)
    return ProjectResponse(data=await _out(db, current_user.id, project))


@router.get("/projects/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: uuid.UUID, current_user: ActiveUser, db: DbSession
) -> ProjectResponse:
    project = await ResearchProjectService(db).get(current_user.id, project_id)
    return ProjectResponse(data=await _out(db, current_user.id, project))


@router.patch("/projects/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: uuid.UUID, body: ProjectPatch, current_user: ActiveUser, db: DbSession
) -> ProjectResponse:
    project = await ResearchProjectService(db).update(current_user.id, project_id, body)
    return ProjectResponse(data=await _out(db, current_user.id, project))


@router.post("/projects/{project_id}/archive", response_model=ProjectResponse)
async def archive_project(
    project_id: uuid.UUID, current_user: ActiveUser, db: DbSession
) -> ProjectResponse:
    project = await ResearchProjectService(db).archive(current_user.id, project_id)
    return ProjectResponse(data=await _out(db, current_user.id, project))


@router.post("/projects/{project_id}/restore", response_model=ProjectResponse)
async def restore_project(
    project_id: uuid.UUID, current_user: ActiveUser, db: DbSession
) -> ProjectResponse:
    project = await ResearchProjectService(db).restore(current_user.id, project_id)
    return ProjectResponse(data=await _out(db, current_user.id, project))


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(project_id: uuid.UUID, current_user: ActiveUser, db: DbSession) -> None:
    await ResearchProjectService(db).delete(current_user.id, project_id)
