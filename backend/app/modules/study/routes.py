"""Study generation routes (spec 19.1, generic form for M0; per-generator endpoints arrive with each
generator). Every route needs an active session; ownership is checked in the service."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response

from app.ai.orchestration.runtime import AiRuntime, Runtime
from app.core.dependencies import ActiveUser, DbSession
from app.core.rate_limit import get_rate_limiter
from app.models.generation_job import GenerationJob
from app.modules.study.schemas import (
    GenerationJobListResponse,
    GenerationJobOut,
    GenerationJobResponse,
    GenerationRequest,
    GeneratorListResponse,
    GeneratorOut,
    StudyMaterialOut,
    StudyMaterialResponse,
)
from app.modules.study.service import StudyGenerationService
from app.study.dispatch import GenerationDispatcher, get_generation_dispatcher
from app.study.errors import safe_job_message

router = APIRouter(prefix="/study", tags=["study"])

_MAX_LIMIT = 100
Dispatcher = Annotated[GenerationDispatcher, Depends(get_generation_dispatcher)]


def _service(
    db: DbSession, runtime: AiRuntime, dispatcher: GenerationDispatcher
) -> StudyGenerationService:
    return StudyGenerationService(db, runtime, dispatcher, get_rate_limiter())


def _out(job: GenerationJob, *, existing: bool = False) -> GenerationJobOut:
    out = GenerationJobOut.model_validate(job)
    out.error_message = safe_job_message(job.error_code)
    out.existing = existing
    return out


@router.get("/generators", response_model=GeneratorListResponse)
async def list_generators(
    current_user: ActiveUser, db: DbSession, runtime: Runtime, dispatcher: Dispatcher
) -> GeneratorListResponse:
    items = _service(db, runtime, dispatcher).generators()
    return GeneratorListResponse(
        data=[GeneratorOut(key=k, resource_type=r, settings_schema=s) for k, r, s in items]
    )


@router.post("/generations", response_model=GenerationJobResponse, status_code=202)
async def create_generation(
    body: GenerationRequest,
    response: Response,
    current_user: ActiveUser,
    db: DbSession,
    runtime: Runtime,
    dispatcher: Dispatcher,
) -> GenerationJobResponse:
    """202 for a new job; 200 with `existing: true` when an identical request is already running."""
    job, existing = await _service(db, runtime, dispatcher).create(current_user, body)
    if existing:
        response.status_code = 200
    return GenerationJobResponse(data=_out(job, existing=existing))


@router.get("/generations", response_model=GenerationJobListResponse)
async def list_generations(
    current_user: ActiveUser,
    db: DbSession,
    runtime: Runtime,
    dispatcher: Dispatcher,
    status: Literal[
        "pending",
        "retrieving_sources",
        "generating",
        "validating",
        "saving",
        "completed",
        "failed",
        "cancelled",
    ]
    | None = None,
    limit: int = Query(20, ge=1, le=_MAX_LIMIT),
    offset: int = Query(0, ge=0),
) -> GenerationJobListResponse:
    jobs, total = await _service(db, runtime, dispatcher).list(
        current_user, status=status, limit=limit, offset=offset
    )
    return GenerationJobListResponse(
        data=[_out(j) for j in jobs], total=total, limit=limit, offset=offset
    )


@router.get("/generations/{job_id}", response_model=GenerationJobResponse)
async def get_generation(
    job_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
    runtime: Runtime,
    dispatcher: Dispatcher,
) -> GenerationJobResponse:
    return GenerationJobResponse(
        data=_out(await _service(db, runtime, dispatcher).get(current_user, job_id))
    )


@router.post("/generations/{job_id}/cancel", response_model=GenerationJobResponse)
async def cancel_generation(
    job_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
    runtime: Runtime,
    dispatcher: Dispatcher,
) -> GenerationJobResponse:
    return GenerationJobResponse(
        data=_out(await _service(db, runtime, dispatcher).cancel(current_user, job_id))
    )


@router.get("/materials/{material_id}", response_model=StudyMaterialResponse)
async def get_material(
    material_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
    runtime: Runtime,
    dispatcher: Dispatcher,
) -> StudyMaterialResponse:
    material = await _service(db, runtime, dispatcher).get_material(current_user, material_id)
    return StudyMaterialResponse(data=StudyMaterialOut.model_validate(material))
