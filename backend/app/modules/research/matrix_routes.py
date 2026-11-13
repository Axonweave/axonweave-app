"""Evidence matrix routes (Phase 7 M7.5). Every route needs an active session; writes are covered by
CSRF protection (D-04); ownership is checked in the service (a foreign id is a 404)."""

import uuid

from fastapi import APIRouter, Query, Response

from app.core.dependencies import ActiveUser, DbSession
from app.modules.research.matrix_schemas import (
    ResearchMatrixAddPapers,
    ResearchMatrixColumnCreate,
    ResearchMatrixColumnOrder,
    ResearchMatrixColumnPatch,
    ResearchMatrixCreate,
    ResearchMatrixEntryPatch,
    ResearchMatrixListResponse,
    ResearchMatrixPatch,
    ResearchMatrixResponse,
)
from app.modules.research.matrix_service import ResearchMatrixService

router = APIRouter(prefix="/research", tags=["research"])


@router.post(
    "/projects/{project_id}/matrices", response_model=ResearchMatrixResponse, status_code=201
)
async def create_matrix(
    project_id: uuid.UUID, body: ResearchMatrixCreate, current_user: ActiveUser, db: DbSession
) -> ResearchMatrixResponse:
    return ResearchMatrixResponse(
        data=await ResearchMatrixService(db).create(current_user.id, project_id, body)
    )


@router.get("/projects/{project_id}/matrices", response_model=ResearchMatrixListResponse)
async def list_matrices(
    project_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> ResearchMatrixListResponse:
    data, total = await ResearchMatrixService(db).list(
        current_user.id, project_id, limit=limit, offset=offset
    )
    return ResearchMatrixListResponse(data=data, total=total, limit=limit, offset=offset)


@router.get("/matrices/{matrix_id}", response_model=ResearchMatrixResponse)
async def get_matrix(
    matrix_id: uuid.UUID, current_user: ActiveUser, db: DbSession
) -> ResearchMatrixResponse:
    return ResearchMatrixResponse(
        data=await ResearchMatrixService(db).get(current_user.id, matrix_id)
    )


@router.patch("/matrices/{matrix_id}", response_model=ResearchMatrixResponse)
async def edit_matrix(
    matrix_id: uuid.UUID, body: ResearchMatrixPatch, current_user: ActiveUser, db: DbSession
) -> ResearchMatrixResponse:
    return ResearchMatrixResponse(
        data=await ResearchMatrixService(db).patch(current_user.id, matrix_id, body)
    )


@router.delete("/matrices/{matrix_id}", status_code=204)
async def delete_matrix(matrix_id: uuid.UUID, current_user: ActiveUser, db: DbSession) -> Response:
    await ResearchMatrixService(db).delete(current_user.id, matrix_id)
    return Response(status_code=204)


@router.post("/matrices/{matrix_id}/papers", response_model=ResearchMatrixResponse)
async def add_matrix_papers(
    matrix_id: uuid.UUID, body: ResearchMatrixAddPapers, current_user: ActiveUser, db: DbSession
) -> ResearchMatrixResponse:
    return ResearchMatrixResponse(
        data=await ResearchMatrixService(db).add_papers(current_user.id, matrix_id, body.paper_ids)
    )


@router.delete("/matrices/{matrix_id}/papers/{paper_id}", response_model=ResearchMatrixResponse)
async def remove_matrix_paper(
    matrix_id: uuid.UUID, paper_id: uuid.UUID, current_user: ActiveUser, db: DbSession
) -> ResearchMatrixResponse:
    return ResearchMatrixResponse(
        data=await ResearchMatrixService(db).remove_paper(current_user.id, matrix_id, paper_id)
    )


@router.post(
    "/matrices/{matrix_id}/columns", response_model=ResearchMatrixResponse, status_code=201
)
async def add_matrix_column(
    matrix_id: uuid.UUID, body: ResearchMatrixColumnCreate, current_user: ActiveUser, db: DbSession
) -> ResearchMatrixResponse:
    return ResearchMatrixResponse(
        data=await ResearchMatrixService(db).add_column(current_user.id, matrix_id, body)
    )


@router.put("/matrices/{matrix_id}/columns/order", response_model=ResearchMatrixResponse)
async def reorder_matrix_columns(
    matrix_id: uuid.UUID, body: ResearchMatrixColumnOrder, current_user: ActiveUser, db: DbSession
) -> ResearchMatrixResponse:
    return ResearchMatrixResponse(
        data=await ResearchMatrixService(db).reorder_columns(
            current_user.id, matrix_id, body.column_ids
        )
    )


@router.patch("/matrices/{matrix_id}/columns/{column_id}", response_model=ResearchMatrixResponse)
async def rename_matrix_column(
    matrix_id: uuid.UUID,
    column_id: uuid.UUID,
    body: ResearchMatrixColumnPatch,
    current_user: ActiveUser,
    db: DbSession,
) -> ResearchMatrixResponse:
    return ResearchMatrixResponse(
        data=await ResearchMatrixService(db).rename_column(
            current_user.id, matrix_id, column_id, body.title
        )
    )


@router.delete("/matrices/{matrix_id}/columns/{column_id}", response_model=ResearchMatrixResponse)
async def remove_matrix_column(
    matrix_id: uuid.UUID, column_id: uuid.UUID, current_user: ActiveUser, db: DbSession
) -> ResearchMatrixResponse:
    return ResearchMatrixResponse(
        data=await ResearchMatrixService(db).remove_column(current_user.id, matrix_id, column_id)
    )


@router.patch(
    "/matrices/{matrix_id}/entries/{paper_id}/{column_id}", response_model=ResearchMatrixResponse
)
async def edit_matrix_entry(
    matrix_id: uuid.UUID,
    paper_id: uuid.UUID,
    column_id: uuid.UUID,
    body: ResearchMatrixEntryPatch,
    current_user: ActiveUser,
    db: DbSession,
) -> ResearchMatrixResponse:
    return ResearchMatrixResponse(
        data=await ResearchMatrixService(db).edit_entry(
            current_user.id, matrix_id, paper_id, column_id, body.value
        )
    )


@router.post("/matrices/{matrix_id}/refresh", response_model=ResearchMatrixResponse)
async def refresh_matrix(
    matrix_id: uuid.UUID, current_user: ActiveUser, db: DbSession
) -> ResearchMatrixResponse:
    """Re-read the paper analyses into cells that still hold extracted values. Researcher-written
    cells are never overwritten."""
    return ResearchMatrixResponse(
        data=await ResearchMatrixService(db).refresh(current_user.id, matrix_id)
    )
