"""Knowledge routes. Milestone 6.1/6.2 adds extraction only (spec 11.2: POST /knowledge/extract and
GET /knowledge/extract/{job_id}, plus list and cancel); graph reads and edits arrive in 6.3.
Every route needs an active session; ownership is checked in the service."""

import uuid
from dataclasses import asdict
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response

from app.ai.orchestration.runtime import AiRuntime, Runtime
from app.core.dependencies import ActiveUser, DbSession
from app.core.rate_limit import get_rate_limiter
from app.knowledge.dispatch import ExtractionDispatcher, get_extraction_dispatcher
from app.knowledge.errors import safe_job_message
from app.models.knowledge import KnowledgeExtractionJob
from app.modules.knowledge.schemas import (
    ExtractionJobListResponse,
    ExtractionJobOut,
    ExtractionJobResponse,
    ExtractRequest,
    ExtractSubjectRequest,
    ExtractWebRequest,
    SubjectRunOut,
    SubjectRunResponse,
)
from app.modules.knowledge.service import KnowledgeExtractionService

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

_MAX_LIMIT = 100
Dispatcher = Annotated[ExtractionDispatcher, Depends(get_extraction_dispatcher)]


def _service(
    db: DbSession, runtime: AiRuntime, dispatcher: ExtractionDispatcher
) -> KnowledgeExtractionService:
    return KnowledgeExtractionService(db, runtime, dispatcher, get_rate_limiter())


def _out(job: KnowledgeExtractionJob, *, existing: bool = False) -> ExtractionJobOut:
    out = ExtractionJobOut.model_validate(job)
    out.error_message = safe_job_message(job.error_code)
    out.existing = existing
    return out


@router.post("/extract", response_model=ExtractionJobResponse, status_code=202)
async def create_extraction(
    body: ExtractRequest,
    response: Response,
    current_user: ActiveUser,
    db: DbSession,
    runtime: Runtime,
    dispatcher: Dispatcher,
) -> ExtractionJobResponse:
    """202 for a new job; 200 with `existing: true` when an identical request is already running."""
    job, existing = await _service(db, runtime, dispatcher).create(current_user, body.document_id)
    if existing:
        response.status_code = 200
    return ExtractionJobResponse(data=_out(job, existing=existing))


@router.post("/extract/subject", response_model=SubjectRunResponse, status_code=202)
async def create_subject_extraction(
    body: ExtractSubjectRequest,
    current_user: ActiveUser,
    db: DbSession,
    runtime: Runtime,
    dispatcher: Dispatcher,
) -> SubjectRunResponse:
    """Queue extraction for every ready document of a subject that has none yet."""
    result = await _service(db, runtime, dispatcher).create_for_subject(
        current_user, body.subject_id
    )
    return SubjectRunResponse(data=SubjectRunOut(**asdict(result)))


@router.post("/extract/web", response_model=ExtractionJobResponse, status_code=202)
async def create_web_extraction(
    body: ExtractWebRequest,
    response: Response,
    current_user: ActiveUser,
    db: DbSession,
    runtime: Runtime,
    dispatcher: Dispatcher,
) -> ExtractionJobResponse:
    """Build a subject's graph from a web search on its name. 200 with `existing: true` when a web
    run for that subject is already active."""
    job, existing = await _service(db, runtime, dispatcher).create_web(
        current_user, body.subject_id
    )
    if existing:
        response.status_code = 200
    return ExtractionJobResponse(data=_out(job, existing=existing))


@router.get("/extract", response_model=ExtractionJobListResponse)
async def list_extractions(
    current_user: ActiveUser,
    db: DbSession,
    runtime: Runtime,
    dispatcher: Dispatcher,
    status: Literal[
        "pending",
        "retrieving_sources",
        "extracting",
        "validating",
        "saving",
        "completed",
        "failed",
        "cancelled",
    ]
    | None = None,
    document_id: uuid.UUID | None = None,
    subject_id: uuid.UUID | None = None,
    limit: int = Query(20, ge=1, le=_MAX_LIMIT),
    offset: int = Query(0, ge=0),
) -> ExtractionJobListResponse:
    jobs, total = await _service(db, runtime, dispatcher).list(
        current_user,
        status=status,
        document_id=document_id,
        limit=limit,
        offset=offset,
        subject_id=subject_id,
    )
    return ExtractionJobListResponse(
        data=[_out(j) for j in jobs], total=total, limit=limit, offset=offset
    )


@router.get("/extract/{job_id}", response_model=ExtractionJobResponse)
async def get_extraction(
    job_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
    runtime: Runtime,
    dispatcher: Dispatcher,
) -> ExtractionJobResponse:
    return ExtractionJobResponse(
        data=_out(await _service(db, runtime, dispatcher).get(current_user, job_id))
    )


@router.post("/extract/{job_id}/cancel", response_model=ExtractionJobResponse)
async def cancel_extraction(
    job_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
    runtime: Runtime,
    dispatcher: Dispatcher,
) -> ExtractionJobResponse:
    return ExtractionJobResponse(
        data=_out(await _service(db, runtime, dispatcher).cancel(current_user, job_id))
    )
