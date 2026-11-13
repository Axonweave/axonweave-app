"""Citation routes (Phase 7 M7.8). Every route needs an active session; writes are covered by CSRF
protection (D-04); ownership is checked in the service (a foreign id is a 404)."""

import uuid

from fastapi import APIRouter, Query, Response

from app.core.dependencies import ActiveUser, DbSession
from app.modules.research.citation_schemas import (
    ExportFormat,
    ResearchBibliographyResponse,
    ResearchCitationGenerate,
    ResearchCitationListResponse,
    ResearchCitationResponse,
    Style,
)
from app.modules.research.citation_service import ResearchCitationService

router = APIRouter(prefix="/research", tags=["research"])


@router.post("/projects/{project_id}/citations", response_model=ResearchCitationListResponse)
async def generate_citations(
    project_id: uuid.UUID, body: ResearchCitationGenerate, current_user: ActiveUser, db: DbSession
) -> ResearchCitationListResponse:
    data = await ResearchCitationService(db).generate(
        current_user.id, project_id, body.style, body.paper_ids, body.accessed_date
    )
    return ResearchCitationListResponse(data=data, total=len(data))


@router.get("/projects/{project_id}/citations", response_model=ResearchCitationListResponse)
async def list_citations(
    project_id: uuid.UUID, current_user: ActiveUser, db: DbSession, style: Style | None = None
) -> ResearchCitationListResponse:
    data = await ResearchCitationService(db).list(current_user.id, project_id, style)
    return ResearchCitationListResponse(data=data, total=len(data))


@router.get(
    "/projects/{project_id}/citations/bibliography", response_model=ResearchBibliographyResponse
)
async def export_bibliography(
    project_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
    style: Style = "apa",
    export_format: ExportFormat = Query("text", alias="format"),
) -> ResearchBibliographyResponse:
    return ResearchBibliographyResponse(
        data=await ResearchCitationService(db).bibliography(
            current_user.id, project_id, style, export_format
        )
    )


@router.get("/citations/{citation_id}", response_model=ResearchCitationResponse)
async def get_citation(
    citation_id: uuid.UUID, current_user: ActiveUser, db: DbSession
) -> ResearchCitationResponse:
    return ResearchCitationResponse(
        data=await ResearchCitationService(db).get(current_user.id, citation_id)
    )


@router.delete("/citations/{citation_id}", status_code=204)
async def delete_citation(
    citation_id: uuid.UUID, current_user: ActiveUser, db: DbSession
) -> Response:
    await ResearchCitationService(db).delete(current_user.id, citation_id)
    return Response(status_code=204)
