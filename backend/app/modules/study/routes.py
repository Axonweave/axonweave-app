"""Study generation routes (spec 19.1, generic form for M0; per-generator endpoints arrive with each
generator). Every route needs an active session; ownership is checked in the service."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response

from app.ai.orchestration.runtime import AiRuntime, Runtime
from app.core.dependencies import ActiveUser, DbSession
from app.core.rate_limit import get_rate_limiter
from app.models.generation_job import GenerationJob
from app.modules.study.library_service import StudyLibraryService
from app.modules.study.material_service import StudyMaterialService
from app.modules.study.schemas import (
    EditMaterialRequest,
    GenerationJobListResponse,
    GenerationJobOut,
    GenerationJobResponse,
    GenerationRequest,
    GeneratorListResponse,
    GeneratorOut,
    PreviewOut,
    PreviewResponse,
    RegenerateRequest,
    RestoreRequest,
    StudyMaterialOut,
    StudyMaterialResponse,
    VersionListResponse,
    VersionOut,
    VersionResponse,
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
    return StudyMaterialResponse(data=await StudyLibraryService(db).present(current_user.id, material))


def _materials(
    db: DbSession, runtime: AiRuntime, dispatcher: GenerationDispatcher
) -> StudyMaterialService:
    return StudyMaterialService(db, runtime.settings, _service(db, runtime, dispatcher))


@router.patch("/materials/{material_id}", response_model=StudyMaterialResponse)
async def edit_material(
    material_id: uuid.UUID,
    body: EditMaterialRequest,
    current_user: ActiveUser,
    db: DbSession,
    runtime: Runtime,
    dispatcher: Dispatcher,
) -> StudyMaterialResponse:
    """Save the user's edits as a new version (the original generated version is kept)."""
    material = await _materials(db, runtime, dispatcher).edit(
        current_user, material_id, body.expected_version, body.payload
    )
    return StudyMaterialResponse(data=StudyMaterialOut.model_validate(material))


@router.get("/materials/{material_id}/versions", response_model=VersionListResponse)
async def list_versions(
    material_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
    runtime: Runtime,
    dispatcher: Dispatcher,
) -> VersionListResponse:
    rows = await _materials(db, runtime, dispatcher).versions(current_user, material_id)
    return VersionListResponse(
        data=[
            VersionOut(version_number=v.version_number, origin=v.origin, created_at=v.created_at)
            for v in rows
        ]
    )


@router.get("/materials/{material_id}/versions/{number}", response_model=VersionResponse)
async def get_version(
    material_id: uuid.UUID,
    number: int,
    current_user: ActiveUser,
    db: DbSession,
    runtime: Runtime,
    dispatcher: Dispatcher,
) -> VersionResponse:
    v = await _materials(db, runtime, dispatcher).version(current_user, material_id, number)
    return VersionResponse(
        data=VersionOut(
            version_number=v.version_number,
            origin=v.origin,
            created_at=v.created_at,
            content=v.content,
        )
    )


@router.post("/materials/{material_id}/restore", response_model=StudyMaterialResponse)
async def restore_version(
    material_id: uuid.UUID,
    body: RestoreRequest,
    current_user: ActiveUser,
    db: DbSession,
    runtime: Runtime,
    dispatcher: Dispatcher,
) -> StudyMaterialResponse:
    material = await _materials(db, runtime, dispatcher).restore(
        current_user, material_id, body.expected_version, body.version
    )
    return StudyMaterialResponse(data=StudyMaterialOut.model_validate(material))


@router.post(
    "/materials/{material_id}/regenerate", response_model=GenerationJobResponse, status_code=202
)
async def regenerate_material(
    material_id: uuid.UUID,
    body: RegenerateRequest,
    response: Response,
    current_user: ActiveUser,
    db: DbSession,
    runtime: Runtime,
    dispatcher: Dispatcher,
) -> GenerationJobResponse:
    """Starts a job whose result is a preview (`GET /generations/{id}/preview`); nothing is
    replaced until the preview is applied."""
    job, existing = await _materials(db, runtime, dispatcher).regenerate(
        current_user, material_id, section_index=body.section_index, settings=body.settings
    )
    if existing:
        response.status_code = 200
    return GenerationJobResponse(data=_out(job, existing=existing))


@router.get("/generations/{job_id}/preview", response_model=PreviewResponse)
async def get_preview(
    job_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
    runtime: Runtime,
    dispatcher: Dispatcher,
) -> PreviewResponse:
    preview, current = await _materials(db, runtime, dispatcher).preview(current_user, job_id)
    return PreviewResponse(
        data=PreviewOut(
            material_id=uuid.UUID(preview["material_id"]),
            base_version=preview["base_version"],
            current_version=current,
            stale=current != preview["base_version"],
            section_index=preview.get("section_index"),
            content=preview["content"],
        )
    )


@router.post("/generations/{job_id}/preview/apply", response_model=StudyMaterialResponse)
async def apply_preview(
    job_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
    runtime: Runtime,
    dispatcher: Dispatcher,
) -> StudyMaterialResponse:
    material = await _materials(db, runtime, dispatcher).apply_preview(current_user, job_id)
    return StudyMaterialResponse(data=StudyMaterialOut.model_validate(material))


@router.delete("/generations/{job_id}/preview", status_code=204)
async def discard_preview(
    job_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
    runtime: Runtime,
    dispatcher: Dispatcher,
) -> Response:
    await _materials(db, runtime, dispatcher).discard_preview(current_user, job_id)
    return Response(status_code=204)
