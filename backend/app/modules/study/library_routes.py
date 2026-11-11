"""Study library, preferences and export routes (spec 12, 14, 16, 19.2, 19.5). Every route needs an
active session and checks ownership in the service (foreign ids are 404)."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse

from app.core.config import Settings, get_settings
from app.core.dependencies import ActiveUser, DbSession
from app.models.study_export import StudyExport
from app.models.study_material import StudyMaterial
from app.modules.study.export_service import StudyExportService, effective_status
from app.modules.study.library_schemas import (
    ExportOut,
    ExportRequest,
    ExportResponse,
    LibraryItemOut,
    LibraryListResponse,
)
from app.modules.study.library_service import StudyLibraryService, source_document_ids
from app.modules.study.preferences_service import (
    PreferencesIn,
    PreferencesResponse,
    StudyPreferencesService,
)
from app.modules.study.schemas import StudyMaterialResponse
from app.repositories.study_material_repository import StudyMaterialRepository
from app.storage.base import StorageBackend, StorageNotConfiguredError
from app.storage.factory import get_storage_backend
from app.study.dispatch import ExportDispatcher, get_export_dispatcher
from app.study.exporting import CONTENT_TYPES

router = APIRouter(prefix="/study", tags=["study"])

_MAX_LIMIT = 100
AppSettings = Annotated[Settings, Depends(get_settings)]
ExportDispatch = Annotated[ExportDispatcher, Depends(get_export_dispatcher)]
ResourceTypeLiteral = Literal[
    "summary", "flashcards", "quiz", "study_guide", "glossary", "formula_sheet", "question_bank"
]


def get_export_storage() -> StorageBackend:
    """Only export downloads need storage; the rest of the app keeps working without it (D-63)."""
    try:
        return get_storage_backend()
    except StorageNotConfiguredError:
        raise HTTPException(
            503,
            detail={
                "code": "EXPORT_UNAVAILABLE",
                "message": "Exports are not available right now.",
            },
        ) from None


ExportStorage = Annotated[StorageBackend, Depends(get_export_storage)]


def _item(m: StudyMaterial, unavailable: int) -> LibraryItemOut:
    return LibraryItemOut(
        id=m.id,
        title=m.title,
        resource_type=m.resource_type,
        status=m.status,
        workspace_id=m.workspace_id,
        subject_id=m.subject_id,
        chapter_id=m.chapter_id,
        current_version=m.current_version,
        created_at=m.created_at,
        updated_at=m.updated_at,
        archived_at=m.archived_at,
        source_document_count=len(source_document_ids(m)),
        unavailable_source_count=unavailable,
    )


async def _material_out(
    service: StudyLibraryService, user: ActiveUser, material: StudyMaterial
) -> StudyMaterialResponse:
    return StudyMaterialResponse(data=await service.present(user.id, material))


@router.get("/materials", response_model=LibraryListResponse)
async def list_materials(
    current_user: ActiveUser,
    db: DbSession,
    q: Annotated[str | None, Query(max_length=100)] = None,
    resource_type: ResourceTypeLiteral | None = None,
    workspace_id: uuid.UUID | None = None,
    subject_id: uuid.UUID | None = None,
    chapter_id: uuid.UUID | None = None,
    status: Literal["completed", "failed"] | None = None,
    archived: Literal["no", "only", "all"] = "no",
    sort: Literal["created_at", "updated_at", "title", "resource_type"] = "created_at",
    order: Literal["asc", "desc"] = "desc",
    limit: int = Query(20, ge=1, le=_MAX_LIMIT),
    offset: int = Query(0, ge=0, le=100_000),
) -> LibraryListResponse:
    rows, total = await StudyMaterialRepository(db).list_library(
        current_user.id,
        q=q.strip() if q else None,
        resource_type=resource_type,
        workspace_id=workspace_id,
        subject_id=subject_id,
        chapter_id=chapter_id,
        status=status,
        archived=archived,
        sort=sort,
        descending=order == "desc",
        limit=limit,
        offset=offset,
    )
    missing = await StudyLibraryService(db).unavailable_sources(current_user.id, rows)
    return LibraryListResponse(
        data=[_item(m, len(missing.get(m.id, []))) for m in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.delete("/materials/{material_id}", status_code=204)
async def delete_material(
    material_id: uuid.UUID, current_user: ActiveUser, db: DbSession
) -> Response:
    await StudyLibraryService(db).delete(current_user, material_id)
    return Response(status_code=204)


@router.post(
    "/materials/{material_id}/duplicate", response_model=StudyMaterialResponse, status_code=201
)
async def duplicate_material(
    material_id: uuid.UUID, current_user: ActiveUser, db: DbSession
) -> StudyMaterialResponse:
    service = StudyLibraryService(db)
    copy = await service.duplicate(current_user, material_id)
    return await _material_out(service, current_user, copy)


@router.post("/materials/{material_id}/archive", response_model=StudyMaterialResponse)
async def archive_material(
    material_id: uuid.UUID, current_user: ActiveUser, db: DbSession
) -> StudyMaterialResponse:
    service = StudyLibraryService(db)
    material = await service.set_archived(current_user, material_id, True)
    return await _material_out(service, current_user, material)


@router.post("/materials/{material_id}/unarchive", response_model=StudyMaterialResponse)
async def unarchive_material(
    material_id: uuid.UUID, current_user: ActiveUser, db: DbSession
) -> StudyMaterialResponse:
    service = StudyLibraryService(db)
    material = await service.set_archived(current_user, material_id, False)
    return await _material_out(service, current_user, material)


# preferences


@router.get("/preferences", response_model=PreferencesResponse)
async def get_preferences(current_user: ActiveUser, db: DbSession) -> PreferencesResponse:
    return PreferencesResponse(data=await StudyPreferencesService(db).get(current_user))


@router.put("/preferences", response_model=PreferencesResponse)
async def put_preferences(
    body: PreferencesIn, current_user: ActiveUser, db: DbSession
) -> PreferencesResponse:
    return PreferencesResponse(data=await StudyPreferencesService(db).put(current_user, body))


# exports


def _export_out(row: StudyExport) -> ExportOut:
    status = effective_status(row)
    return ExportOut(
        id=row.id,
        study_material_id=row.study_material_id,
        format=row.export_format,  # type: ignore[arg-type]
        status=status,
        size_bytes=row.size_bytes if status == "completed" else None,
        error_code=row.error_code,
        expires_at=row.expires_at,
        created_at=row.created_at,
        download_path=f"/api/v1/study/exports/{row.id}/download" if status == "completed" else None,
    )


@router.post("/materials/{material_id}/export", response_model=ExportResponse, status_code=202)
async def create_export(
    material_id: uuid.UUID,
    body: ExportRequest,
    current_user: ActiveUser,
    db: DbSession,
    settings: AppSettings,
    dispatcher: ExportDispatch,
) -> ExportResponse:
    row = await StudyExportService(db, settings, dispatcher).create(
        current_user, material_id, body.format
    )
    return ExportResponse(data=_export_out(row))


@router.get("/exports/{export_id}", response_model=ExportResponse)
async def get_export(
    export_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
    settings: AppSettings,
    dispatcher: ExportDispatch,
) -> ExportResponse:
    row = await StudyExportService(db, settings, dispatcher).get(current_user, export_id)
    return ExportResponse(data=_export_out(row))


@router.get("/exports/{export_id}/download")
async def download_export(
    export_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
    settings: AppSettings,
    dispatcher: ExportDispatch,
    storage: ExportStorage,
) -> StreamingResponse:
    row, stream = await StudyExportService(db, settings, dispatcher).download(
        current_user, export_id, storage
    )
    return StreamingResponse(
        stream,
        media_type=CONTENT_TYPES[row.export_format],
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            # Fixed name: nothing from the material title ever reaches a header.
            "Content-Disposition": f'attachment; filename="study-export.{row.export_format}"',
            "Content-Length": str(row.size_bytes or 0),
        },
    )
