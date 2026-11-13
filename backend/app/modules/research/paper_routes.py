"""Research paper library routes (Phase 7 M7.2). PDF uploads use the ordinary document upload
(Phase 3 ingestion); the paper is then attached with `document_id`. Every route needs an active
session; writes are covered by CSRF protection (D-04)."""

import uuid

from fastapi import APIRouter, Query

from app.core.dependencies import ActiveUser, DbSession
from app.modules.research.paper_schemas import (
    DuplicateListResponse,
    DuplicateResolve,
    DuplicateResolveOut,
    DuplicateResolveResponse,
    PaperCreate,
    PaperListResponse,
    PaperPatch,
    PaperResponse,
    PaperSortLiteral,
    PaperStatusLiteral,
)
from app.modules.research.paper_service import ResearchPaperService, to_out

router = APIRouter(prefix="/research", tags=["research"])


@router.get("/projects/{project_id}/papers", response_model=PaperListResponse)
async def list_papers(
    project_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
    q: str | None = Query(None, max_length=100),
    status: PaperStatusLiteral | None = None,
    year: int | None = Query(None, ge=1000, le=2200),
    has_file: bool | None = None,
    archived: bool = False,
    sort_by: PaperSortLiteral = "updated_at",
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> PaperListResponse:
    rows, total = await ResearchPaperService(db).list(
        current_user.id,
        project_id,
        q=q,
        status=status,
        year=year,
        has_file=has_file,
        archived=archived,
        sort_by=sort_by,
        descending=sort_dir == "desc",
        limit=limit,
        offset=offset,
    )
    return PaperListResponse(
        data=[to_out(r) for r in rows], total=total, limit=limit, offset=offset
    )


@router.post("/projects/{project_id}/papers", response_model=PaperResponse, status_code=201)
async def create_paper(
    project_id: uuid.UUID, body: PaperCreate, current_user: ActiveUser, db: DbSession
) -> PaperResponse:
    row = await ResearchPaperService(db).create(current_user.id, project_id, body)
    return PaperResponse(data=to_out(row))


@router.get("/projects/{project_id}/papers/duplicates", response_model=DuplicateListResponse)
async def paper_duplicates(
    project_id: uuid.UUID, current_user: ActiveUser, db: DbSession
) -> DuplicateListResponse:
    return DuplicateListResponse(
        data=await ResearchPaperService(db).duplicates(current_user.id, project_id)
    )


@router.post(
    "/projects/{project_id}/papers/duplicates/resolve", response_model=DuplicateResolveResponse
)
async def resolve_paper_duplicate(
    project_id: uuid.UUID, body: DuplicateResolve, current_user: ActiveUser, db: DbSession
) -> DuplicateResolveResponse:
    survivor = await ResearchPaperService(db).resolve_duplicate(current_user.id, project_id, body)
    return DuplicateResolveResponse(data=DuplicateResolveOut(action=body.action, survivor=survivor))


@router.get("/papers/{paper_id}", response_model=PaperResponse)
async def get_paper(paper_id: uuid.UUID, current_user: ActiveUser, db: DbSession) -> PaperResponse:
    return PaperResponse(data=to_out(await ResearchPaperService(db).get(current_user.id, paper_id)))


@router.patch("/papers/{paper_id}", response_model=PaperResponse)
async def update_paper(
    paper_id: uuid.UUID, body: PaperPatch, current_user: ActiveUser, db: DbSession
) -> PaperResponse:
    row = await ResearchPaperService(db).update(current_user.id, paper_id, body)
    return PaperResponse(data=to_out(row))


@router.post("/papers/{paper_id}/archive", response_model=PaperResponse)
async def archive_paper(
    paper_id: uuid.UUID, current_user: ActiveUser, db: DbSession
) -> PaperResponse:
    return PaperResponse(
        data=to_out(await ResearchPaperService(db).archive(current_user.id, paper_id))
    )


@router.post("/papers/{paper_id}/restore", response_model=PaperResponse)
async def restore_paper(
    paper_id: uuid.UUID, current_user: ActiveUser, db: DbSession
) -> PaperResponse:
    return PaperResponse(
        data=to_out(await ResearchPaperService(db).restore(current_user.id, paper_id))
    )


@router.delete("/papers/{paper_id}", status_code=204)
async def delete_paper(paper_id: uuid.UUID, current_user: ActiveUser, db: DbSession) -> None:
    await ResearchPaperService(db).delete(current_user.id, paper_id)
