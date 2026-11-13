"""Contradiction routes (Phase 7 M7.7). Every route needs an active session; writes are covered by
CSRF protection (D-04); ownership is checked in the service (a foreign id is a 404)."""

import uuid

from fastapi import APIRouter, Query, Response

from app.core.dependencies import ActiveUser, DbSession
from app.modules.research.contradiction_schemas import (
    Category,
    ResearchContradictionGenerate,
    ResearchContradictionListResponse,
    ResearchContradictionPatch,
    ResearchContradictionResponse,
    Review,
)
from app.modules.research.contradiction_service import ResearchContradictionService

router = APIRouter(prefix="/research", tags=["research"])


@router.post(
    "/projects/{project_id}/contradictions/generate",
    response_model=ResearchContradictionListResponse,
)
async def generate_contradictions(
    project_id: uuid.UUID,
    body: ResearchContradictionGenerate,
    current_user: ActiveUser,
    db: DbSession,
) -> ResearchContradictionListResponse:
    data = await ResearchContradictionService(db).generate(
        current_user.id, project_id, body.paper_ids
    )
    return ResearchContradictionListResponse(
        data=data, total=len(data), limit=max(len(data), 1), offset=0
    )


@router.get(
    "/projects/{project_id}/contradictions", response_model=ResearchContradictionListResponse
)
async def list_contradictions(
    project_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
    category: Category | None = None,
    review_status: Review | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> ResearchContradictionListResponse:
    data, total = await ResearchContradictionService(db).list(
        current_user.id,
        project_id,
        category=category,
        review_status=review_status,
        limit=limit,
        offset=offset,
    )
    return ResearchContradictionListResponse(data=data, total=total, limit=limit, offset=offset)


@router.get("/contradictions/{contradiction_id}", response_model=ResearchContradictionResponse)
async def get_contradiction(
    contradiction_id: uuid.UUID, current_user: ActiveUser, db: DbSession
) -> ResearchContradictionResponse:
    return ResearchContradictionResponse(
        data=await ResearchContradictionService(db).get(current_user.id, contradiction_id)
    )


@router.patch("/contradictions/{contradiction_id}", response_model=ResearchContradictionResponse)
async def review_contradiction(
    contradiction_id: uuid.UUID,
    body: ResearchContradictionPatch,
    current_user: ActiveUser,
    db: DbSession,
) -> ResearchContradictionResponse:
    return ResearchContradictionResponse(
        data=await ResearchContradictionService(db).patch(current_user.id, contradiction_id, body)
    )


@router.delete("/contradictions/{contradiction_id}", status_code=204)
async def delete_contradiction(
    contradiction_id: uuid.UUID, current_user: ActiveUser, db: DbSession
) -> Response:
    await ResearchContradictionService(db).delete(current_user.id, contradiction_id)
    return Response(status_code=204)
