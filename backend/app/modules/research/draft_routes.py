"""Draft routes (Phase 7 M7.9). Every route needs an active session; writes are covered by CSRF
protection (D-04); ownership is checked in the service (a foreign id is a 404)."""

import uuid

from fastapi import APIRouter, Query, Response

from app.ai.orchestration.runtime import Runtime
from app.core.dependencies import ActiveUser, DbSession
from app.modules.research.draft_schemas import (
    DraftStatus,
    ResearchDraftCheckResponse,
    ResearchDraftCreate,
    ResearchDraftExportResponse,
    ResearchDraftListResponse,
    ResearchDraftPatch,
    ResearchDraftResponse,
    ResearchDraftRestore,
    ResearchDraftVersionListResponse,
    ResearchDraftVersionResponse,
    ResearchWritingRequest,
    ResearchWritingResponse,
)
from app.modules.research.draft_service import ResearchDraftService

router = APIRouter(prefix="/research", tags=["research"])


@router.post("/projects/{project_id}/drafts", response_model=ResearchDraftResponse, status_code=201)
async def create_draft(
    project_id: uuid.UUID, body: ResearchDraftCreate, current_user: ActiveUser, db: DbSession
) -> ResearchDraftResponse:
    return ResearchDraftResponse(
        data=await ResearchDraftService(db).create(current_user.id, project_id, body)
    )


@router.get("/projects/{project_id}/drafts", response_model=ResearchDraftListResponse)
async def list_drafts(
    project_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
    status: DraftStatus | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> ResearchDraftListResponse:
    data, total = await ResearchDraftService(db).list(
        current_user.id, project_id, status=status, limit=limit, offset=offset
    )
    return ResearchDraftListResponse(data=data, total=total, limit=limit, offset=offset)


@router.get("/drafts/{draft_id}", response_model=ResearchDraftResponse)
async def get_draft(
    draft_id: uuid.UUID, current_user: ActiveUser, db: DbSession
) -> ResearchDraftResponse:
    return ResearchDraftResponse(data=await ResearchDraftService(db).get(current_user.id, draft_id))


@router.patch("/drafts/{draft_id}", response_model=ResearchDraftResponse)
async def edit_draft(
    draft_id: uuid.UUID, body: ResearchDraftPatch, current_user: ActiveUser, db: DbSession
) -> ResearchDraftResponse:
    return ResearchDraftResponse(
        data=await ResearchDraftService(db).patch(current_user.id, draft_id, body)
    )


@router.delete("/drafts/{draft_id}", status_code=204)
async def delete_draft(draft_id: uuid.UUID, current_user: ActiveUser, db: DbSession) -> Response:
    await ResearchDraftService(db).delete(current_user.id, draft_id)
    return Response(status_code=204)


@router.get("/drafts/{draft_id}/versions", response_model=ResearchDraftVersionListResponse)
async def list_versions(
    draft_id: uuid.UUID, current_user: ActiveUser, db: DbSession
) -> ResearchDraftVersionListResponse:
    return ResearchDraftVersionListResponse(
        data=await ResearchDraftService(db).versions(current_user.id, draft_id)
    )


@router.get("/drafts/{draft_id}/versions/{number}", response_model=ResearchDraftVersionResponse)
async def get_version(
    draft_id: uuid.UUID, number: int, current_user: ActiveUser, db: DbSession
) -> ResearchDraftVersionResponse:
    return ResearchDraftVersionResponse(
        data=await ResearchDraftService(db).version(current_user.id, draft_id, number)
    )


@router.post("/drafts/{draft_id}/versions/{number}/restore", response_model=ResearchDraftResponse)
async def restore_version(
    draft_id: uuid.UUID,
    number: int,
    body: ResearchDraftRestore,
    current_user: ActiveUser,
    db: DbSession,
) -> ResearchDraftResponse:
    return ResearchDraftResponse(
        data=await ResearchDraftService(db).restore(
            current_user.id, draft_id, number, body.expected_version
        )
    )


@router.post("/drafts/{draft_id}/check", response_model=ResearchDraftCheckResponse)
async def check_draft(
    draft_id: uuid.UUID, current_user: ActiveUser, db: DbSession
) -> ResearchDraftCheckResponse:
    return ResearchDraftCheckResponse(
        data=await ResearchDraftService(db).check(current_user.id, draft_id)
    )


@router.get("/drafts/{draft_id}/preview", response_model=ResearchDraftExportResponse)
async def preview_draft(
    draft_id: uuid.UUID, current_user: ActiveUser, db: DbSession
) -> ResearchDraftExportResponse:
    return ResearchDraftExportResponse(
        data=await ResearchDraftService(db).render(current_user.id, draft_id, strict=False)
    )


@router.get("/drafts/{draft_id}/export", response_model=ResearchDraftExportResponse)
async def export_draft(
    draft_id: uuid.UUID, current_user: ActiveUser, db: DbSession
) -> ResearchDraftExportResponse:
    """Markdown only; refused while the draft cites papers that are not in its project."""
    return ResearchDraftExportResponse(
        data=await ResearchDraftService(db).render(current_user.id, draft_id, strict=True)
    )


@router.post("/drafts/{draft_id}/assist", response_model=ResearchWritingResponse)
async def assist_draft(
    draft_id: uuid.UUID,
    body: ResearchWritingRequest,
    current_user: ActiveUser,
    db: DbSession,
    runtime: Runtime,
) -> ResearchWritingResponse:
    """Returns a suggestion; nothing is saved until the researcher accepts it as an edit."""
    return ResearchWritingResponse(
        data=await ResearchDraftService(db, runtime).assist(current_user.id, draft_id, body)
    )
