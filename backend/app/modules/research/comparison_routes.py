"""Paper comparison routes (Phase 7 M7.4). Every route needs an active session; writes are covered
by CSRF protection (D-04); ownership is checked in the service (a foreign id is a 404)."""

import uuid

from fastapi import APIRouter, Query, Response

from app.core.dependencies import ActiveUser, DbSession
from app.modules.research.comparison_schemas import (
    ResearchComparisonCreate,
    ResearchComparisonListResponse,
    ResearchComparisonPatch,
    ResearchComparisonResponse,
)
from app.modules.research.comparison_service import ResearchComparisonService

router = APIRouter(prefix="/research", tags=["research"])


@router.post(
    "/projects/{project_id}/comparisons",
    response_model=ResearchComparisonResponse,
    status_code=201,
)
async def create_comparison(
    project_id: uuid.UUID,
    body: ResearchComparisonCreate,
    current_user: ActiveUser,
    db: DbSession,
) -> ResearchComparisonResponse:
    data = await ResearchComparisonService(db).create(current_user.id, project_id, body)
    return ResearchComparisonResponse(data=data)


@router.get("/projects/{project_id}/comparisons", response_model=ResearchComparisonListResponse)
async def list_comparisons(
    project_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> ResearchComparisonListResponse:
    data, total = await ResearchComparisonService(db).list(
        current_user.id, project_id, limit=limit, offset=offset
    )
    return ResearchComparisonListResponse(data=data, total=total, limit=limit, offset=offset)


@router.get("/comparisons/{comparison_id}", response_model=ResearchComparisonResponse)
async def get_comparison(
    comparison_id: uuid.UUID, current_user: ActiveUser, db: DbSession
) -> ResearchComparisonResponse:
    return ResearchComparisonResponse(
        data=await ResearchComparisonService(db).get(current_user.id, comparison_id)
    )


@router.patch("/comparisons/{comparison_id}", response_model=ResearchComparisonResponse)
async def edit_comparison(
    comparison_id: uuid.UUID,
    body: ResearchComparisonPatch,
    current_user: ActiveUser,
    db: DbSession,
) -> ResearchComparisonResponse:
    return ResearchComparisonResponse(
        data=await ResearchComparisonService(db).patch(current_user.id, comparison_id, body)
    )


@router.delete("/comparisons/{comparison_id}", status_code=204)
async def delete_comparison(
    comparison_id: uuid.UUID, current_user: ActiveUser, db: DbSession
) -> Response:
    await ResearchComparisonService(db).delete(current_user.id, comparison_id)
    return Response(status_code=204)
