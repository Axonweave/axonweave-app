"""Research gap routes (Phase 7 M7.6). Every route needs an active session; writes are covered by
CSRF protection (D-04); ownership is checked in the service (a foreign id is a 404)."""

import uuid

from fastapi import APIRouter, Query, Response

from app.core.dependencies import ActiveUser, DbSession
from app.modules.research.gap_schemas import (
    Category,
    ResearchGapGenerate,
    ResearchGapListResponse,
    ResearchGapPatch,
    ResearchGapResponse,
    Status,
)
from app.modules.research.gap_service import ResearchGapService

router = APIRouter(prefix="/research", tags=["research"])


@router.post("/projects/{project_id}/gaps/generate", response_model=ResearchGapListResponse)
async def generate_gaps(
    project_id: uuid.UUID, body: ResearchGapGenerate, current_user: ActiveUser, db: DbSession
) -> ResearchGapListResponse:
    data = await ResearchGapService(db).generate(current_user.id, project_id, body.paper_ids)
    return ResearchGapListResponse(data=data, total=len(data), limit=max(len(data), 1), offset=0)


@router.get("/projects/{project_id}/gaps", response_model=ResearchGapListResponse)
async def list_gaps(
    project_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
    category: Category | None = None,
    status: Status | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> ResearchGapListResponse:
    data, total = await ResearchGapService(db).list(
        current_user.id, project_id, category=category, status=status, limit=limit, offset=offset
    )
    return ResearchGapListResponse(data=data, total=total, limit=limit, offset=offset)


@router.get("/gaps/{gap_id}", response_model=ResearchGapResponse)
async def get_gap(
    gap_id: uuid.UUID, current_user: ActiveUser, db: DbSession
) -> ResearchGapResponse:
    return ResearchGapResponse(data=await ResearchGapService(db).get(current_user.id, gap_id))


@router.patch("/gaps/{gap_id}", response_model=ResearchGapResponse)
async def edit_gap(
    gap_id: uuid.UUID, body: ResearchGapPatch, current_user: ActiveUser, db: DbSession
) -> ResearchGapResponse:
    return ResearchGapResponse(
        data=await ResearchGapService(db).patch(current_user.id, gap_id, body)
    )


@router.delete("/gaps/{gap_id}", status_code=204)
async def delete_gap(gap_id: uuid.UUID, current_user: ActiveUser, db: DbSession) -> Response:
    await ResearchGapService(db).delete(current_user.id, gap_id)
    return Response(status_code=204)
