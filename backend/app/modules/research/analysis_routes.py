"""Paper analysis and notes routes (Phase 7 M7.3). Every route needs an active session; writes are
covered by CSRF protection (D-04); ownership of the paper (and its project) is checked in the
service, so a foreign id is a 404."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.ai.orchestration.runtime import AiRuntime, Runtime
from app.core.dependencies import ActiveUser, DbSession
from app.core.rate_limit import get_rate_limiter
from app.knowledge.dispatch import ExtractionDispatcher
from app.modules.research.analysis_schemas import (
    PaperAnalysisResponse,
    PaperAnalysisRunListResponse,
    PaperAnalysisRunResponse,
    PaperNoteCreate,
    PaperNoteListResponse,
    PaperNoteOut,
    PaperNotePatch,
    PaperNoteResponse,
)
from app.modules.research.analysis_service import PaperAnalysisService, run_out
from app.research.analysis_dispatch import get_analysis_dispatcher

router = APIRouter(prefix="/research", tags=["research"])

Dispatcher = Annotated[ExtractionDispatcher, Depends(get_analysis_dispatcher)]


def _service(
    db: DbSession, runtime: AiRuntime, dispatcher: ExtractionDispatcher
) -> PaperAnalysisService:
    return PaperAnalysisService(db, runtime, dispatcher, get_rate_limiter())


@router.post(
    "/papers/{paper_id}/analyses", response_model=PaperAnalysisRunResponse, status_code=202
)
async def start_analysis(
    paper_id: uuid.UUID,
    response: Response,
    current_user: ActiveUser,
    db: DbSession,
    runtime: Runtime,
    dispatcher: Dispatcher,
) -> PaperAnalysisRunResponse:
    """202 for a new analysis; 200 with `existing: true` when one is already running."""
    run, existing = await _service(db, runtime, dispatcher).start(current_user, paper_id)
    if existing:
        response.status_code = 200
    return PaperAnalysisRunResponse(data=run_out(run, existing=existing))


@router.get("/papers/{paper_id}/analyses", response_model=PaperAnalysisRunListResponse)
async def analysis_history(
    paper_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
    runtime: Runtime,
    dispatcher: Dispatcher,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> PaperAnalysisRunListResponse:
    runs, total = await _service(db, runtime, dispatcher).history(
        current_user, paper_id, limit=limit, offset=offset
    )
    return PaperAnalysisRunListResponse(
        data=[run_out(r) for r in runs], total=total, limit=limit, offset=offset
    )


@router.get("/papers/{paper_id}/analysis", response_model=PaperAnalysisResponse)
async def get_analysis(
    paper_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
    runtime: Runtime,
    dispatcher: Dispatcher,
    version: int | None = Query(None, ge=1),
) -> PaperAnalysisResponse:
    return PaperAnalysisResponse(
        data=await _service(db, runtime, dispatcher).analysis(current_user, paper_id, version)
    )


@router.get("/papers/{paper_id}/analyses/{extraction_id}", response_model=PaperAnalysisRunResponse)
async def get_analysis_run(
    paper_id: uuid.UUID,
    extraction_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
    runtime: Runtime,
    dispatcher: Dispatcher,
) -> PaperAnalysisRunResponse:
    run = await _service(db, runtime, dispatcher).get_run(current_user, paper_id, extraction_id)
    return PaperAnalysisRunResponse(data=run_out(run))


@router.post(
    "/papers/{paper_id}/analyses/{extraction_id}/cancel", response_model=PaperAnalysisRunResponse
)
async def cancel_analysis(
    paper_id: uuid.UUID,
    extraction_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
    runtime: Runtime,
    dispatcher: Dispatcher,
) -> PaperAnalysisRunResponse:
    run = await _service(db, runtime, dispatcher).cancel(current_user, paper_id, extraction_id)
    return PaperAnalysisRunResponse(data=run_out(run))


# notes ───────────────────────────────────────────────────────────────────────


@router.get("/papers/{paper_id}/notes", response_model=PaperNoteListResponse)
async def list_notes(
    paper_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
    runtime: Runtime,
    dispatcher: Dispatcher,
) -> PaperNoteListResponse:
    notes = await _service(db, runtime, dispatcher).list_notes(current_user, paper_id)
    return PaperNoteListResponse(data=[PaperNoteOut.model_validate(n) for n in notes])


@router.post("/papers/{paper_id}/notes", response_model=PaperNoteResponse, status_code=201)
async def create_note(
    paper_id: uuid.UUID,
    body: PaperNoteCreate,
    current_user: ActiveUser,
    db: DbSession,
    runtime: Runtime,
    dispatcher: Dispatcher,
) -> PaperNoteResponse:
    note = await _service(db, runtime, dispatcher).add_note(current_user, paper_id, body)
    return PaperNoteResponse(data=PaperNoteOut.model_validate(note))


@router.patch("/notes/{note_id}", response_model=PaperNoteResponse)
async def edit_note(
    note_id: uuid.UUID,
    body: PaperNotePatch,
    current_user: ActiveUser,
    db: DbSession,
    runtime: Runtime,
    dispatcher: Dispatcher,
) -> PaperNoteResponse:
    note = await _service(db, runtime, dispatcher).edit_note(current_user, note_id, body.body)
    return PaperNoteResponse(data=PaperNoteOut.model_validate(note))


@router.delete("/notes/{note_id}", status_code=204)
async def delete_note(
    note_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
    runtime: Runtime,
    dispatcher: Dispatcher,
) -> Response:
    await _service(db, runtime, dispatcher).delete_note(current_user, note_id)
    return Response(status_code=204)
