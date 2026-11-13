"""Concept link routes (Phase 7 M7.10). Every route needs an active session; writes are covered by
CSRF protection (D-04); ownership is checked in the service (a foreign id is a 404)."""

import uuid

from fastapi import APIRouter, Query, Response

from app.core.dependencies import ActiveUser, DbSession
from app.modules.research.concept_schemas import (
    LinkStatus,
    ResearchConceptLinkListResponse,
    ResearchConceptLinkPatch,
    ResearchConceptLinkResponse,
    ResearchConceptResearchResponse,
    ResearchConceptSuggest,
)
from app.modules.research.concept_service import ResearchConceptService

router = APIRouter(prefix="/research", tags=["research"])


@router.post(
    "/projects/{project_id}/concept-links/suggest", response_model=ResearchConceptLinkListResponse
)
async def suggest_concept_links(
    project_id: uuid.UUID, body: ResearchConceptSuggest, current_user: ActiveUser, db: DbSession
) -> ResearchConceptLinkListResponse:
    data = await ResearchConceptService(db).suggest(current_user.id, project_id, body.paper_ids)
    return ResearchConceptLinkListResponse(
        data=data, total=len(data), limit=max(len(data), 1), offset=0
    )


@router.get("/projects/{project_id}/concept-links", response_model=ResearchConceptLinkListResponse)
async def list_concept_links(
    project_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
    paper_id: uuid.UUID | None = None,
    link_status: LinkStatus | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> ResearchConceptLinkListResponse:
    data, total = await ResearchConceptService(db).list(
        current_user.id,
        project_id,
        paper_id=paper_id,
        status=link_status,
        limit=limit,
        offset=offset,
    )
    return ResearchConceptLinkListResponse(data=data, total=total, limit=limit, offset=offset)


@router.patch("/concept-links/{link_id}", response_model=ResearchConceptLinkResponse)
async def review_concept_link(
    link_id: uuid.UUID, body: ResearchConceptLinkPatch, current_user: ActiveUser, db: DbSession
) -> ResearchConceptLinkResponse:
    return ResearchConceptLinkResponse(
        data=await ResearchConceptService(db).set_status(current_user.id, link_id, body.link_status)
    )


@router.delete("/concept-links/{link_id}", status_code=204)
async def delete_concept_link(
    link_id: uuid.UUID, current_user: ActiveUser, db: DbSession
) -> Response:
    await ResearchConceptService(db).delete(current_user.id, link_id)
    return Response(status_code=204)


@router.get("/papers/{paper_id}/concepts", response_model=ResearchConceptLinkListResponse)
async def paper_concepts(
    paper_id: uuid.UUID, current_user: ActiveUser, db: DbSession
) -> ResearchConceptLinkListResponse:
    data = await ResearchConceptService(db).for_paper(current_user.id, paper_id)
    return ResearchConceptLinkListResponse(
        data=data, total=len(data), limit=max(len(data), 1), offset=0
    )


@router.get("/concepts/{node_id}/research", response_model=ResearchConceptResearchResponse)
async def concept_research(
    node_id: uuid.UUID, current_user: ActiveUser, db: DbSession
) -> ResearchConceptResearchResponse:
    return ResearchConceptResearchResponse(
        data=await ResearchConceptService(db).concept_research(current_user.id, node_id)
    )
