import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.core.config import Settings, get_settings
from app.core.dependencies import ActiveUser, DbSession
from app.core.rate_limit import RateLimiter, get_rate_limiter
from app.modules.documents.scanner import Scanner, get_scanner
from app.modules.documents.schemas import (
    DocumentListResponse,
    DocumentOut,
    DocumentResponse,
    FileTypeLiteral,
    ProcessingStatusOut,
    ProcessingStatusResponse,
    RejectedFile,
    SortField,
    StatusLiteral,
    UpdateDocumentRequest,
    UploadData,
    UploadResponse,
)
from app.modules.documents.service import DocumentService
from app.modules.documents.upload import read_upload_form
from app.storage.base import StorageBackend, StorageNotConfiguredError
from app.storage.factory import get_storage_backend

router = APIRouter(prefix="/documents", tags=["documents"])

_MAX_LIMIT = 100
_INLINE_TYPES = {"pdf", "png", "jpg"}
_NO_STORE = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}


def get_document_storage() -> StorageBackend:
    """Only document endpoints need storage; everything else keeps working without it (D-63)."""
    try:
        return get_storage_backend()
    except StorageNotConfiguredError:
        raise HTTPException(
            503,
            detail={
                "code": "DOCUMENT_STORAGE_NOT_CONFIGURED",
                "message": "Document storage is not configured.",
            },
        ) from None


def get_document_scanner(settings: Annotated[Settings, Depends(get_settings)]) -> Scanner:
    return get_scanner(settings)


Storage = Annotated[StorageBackend, Depends(get_document_storage)]
Scan = Annotated[Scanner, Depends(get_document_scanner)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def _service(
    db: DbSession, storage: StorageBackend, scanner: Scanner, settings: Settings
) -> DocumentService:
    return DocumentService(db, storage, scanner, settings)


def _content_disposition(kind: str, filename: str) -> str:
    ascii_name = filename.encode("ascii", "ignore").decode().replace('"', "") or "document"
    encoded = quote(filename, safe="")
    return f"{kind}; filename=\"{ascii_name}\"; filename*=UTF-8''{encoded}"


async def _stream(source: AsyncIterator[bytes]) -> AsyncIterator[bytes]:
    async for chunk in source:
        yield chunk


@router.post("/upload", response_model=UploadResponse, status_code=201)
async def upload_documents(
    request: Request,
    current_user: ActiveUser,
    db: DbSession,
    storage: Storage,
    scanner: Scan,
    settings: AppSettings,
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> UploadResponse:
    await limiter.check(
        f"doc_upload:{current_user.id}", settings.doc_uploads_per_minute_per_user, 60
    )
    form = await read_upload_form(request, settings)
    outcome = await _service(db, storage, scanner, settings).upload(user=current_user, form=form)
    if not outcome.documents and outcome.rejected:
        _, first = outcome.rejected[0]
        raise HTTPException(
            first.status_code, detail={"code": first.code, "message": first.message}
        )
    return UploadResponse(
        data=UploadData(
            documents=[DocumentOut.model_validate(d) for d in outcome.documents],
            rejected=[
                RejectedFile(filename=name, code=exc.code, message=exc.message)
                for name, exc in outcome.rejected
            ],
        )
    )


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    current_user: ActiveUser,
    db: DbSession,
    storage: Storage,
    scanner: Scan,
    settings: AppSettings,
    workspace_id: uuid.UUID | None = None,
    subject_id: uuid.UUID | None = None,
    folder_id: uuid.UUID | None = None,
    chapter_id: uuid.UUID | None = None,
    status: StatusLiteral | None = None,
    file_type: FileTypeLiteral | None = None,
    q: str | None = Query(default=None, max_length=255),
    include_archived: bool = False,
    sort_by: SortField = "created_at",
    sort_dir: Literal["asc", "desc"] = "desc",
    limit: int = Query(default=25, ge=1, le=_MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> DocumentListResponse:
    docs, total = await _service(db, storage, scanner, settings).list_documents(
        user_id=current_user.id,
        workspace_id=workspace_id,
        subject_id=subject_id,
        folder_id=folder_id,
        chapter_id=chapter_id,
        status=status,
        file_type=file_type,
        q=q,
        include_archived=include_archived,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
    )
    return DocumentListResponse(
        data=[DocumentOut.model_validate(d) for d in docs],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
    storage: Storage,
    scanner: Scan,
    settings: AppSettings,
) -> DocumentResponse:
    doc = await _service(db, storage, scanner, settings).get_owned(
        user_id=current_user.id, document_id=document_id
    )
    return DocumentResponse(data=DocumentOut.model_validate(doc))


@router.patch("/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: uuid.UUID,
    data: UpdateDocumentRequest,
    current_user: ActiveUser,
    db: DbSession,
    storage: Storage,
    scanner: Scan,
    settings: AppSettings,
) -> DocumentResponse:
    doc = await _service(db, storage, scanner, settings).update(
        user_id=current_user.id,
        document_id=document_id,
        display_name=data.display_name,
        placement=data.placement,
    )
    return DocumentResponse(data=DocumentOut.model_validate(doc))


@router.post("/{document_id}/archive", response_model=DocumentResponse)
async def archive_document(
    document_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
    storage: Storage,
    scanner: Scan,
    settings: AppSettings,
) -> DocumentResponse:
    doc = await _service(db, storage, scanner, settings).set_archived(
        user_id=current_user.id, document_id=document_id, archived=True
    )
    return DocumentResponse(data=DocumentOut.model_validate(doc))


@router.post("/{document_id}/restore", response_model=DocumentResponse)
async def restore_document(
    document_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
    storage: Storage,
    scanner: Scan,
    settings: AppSettings,
) -> DocumentResponse:
    doc = await _service(db, storage, scanner, settings).set_archived(
        user_id=current_user.id, document_id=document_id, archived=False
    )
    return DocumentResponse(data=DocumentOut.model_validate(doc))


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
    storage: Storage,
    scanner: Scan,
    settings: AppSettings,
) -> None:
    await _service(db, storage, scanner, settings).delete(
        user_id=current_user.id, document_id=document_id
    )


@router.get("/{document_id}/status", response_model=ProcessingStatusResponse)
async def document_status(
    document_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
    storage: Storage,
    scanner: Scan,
    settings: AppSettings,
) -> ProcessingStatusResponse:
    doc, version, job = await _service(db, storage, scanner, settings).processing_status(
        user_id=current_user.id, document_id=document_id
    )
    return ProcessingStatusResponse(
        data=ProcessingStatusOut(
            document_id=doc.id,
            version=doc.latest_version,
            processing_status=version.processing_status if version else doc.processing_status,
            stage=job.stage if job else None,
            job_status=job.status if job else None,
            retry_count=job.retry_count if job else 0,
            error_code=job.error_code if job else None,
            updated_at=job.updated_at if job else doc.updated_at,
        )
    )


@router.get("/{document_id}/download")
async def download_document(
    document_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
    storage: Storage,
    scanner: Scan,
    settings: AppSettings,
) -> StreamingResponse:
    result = await _service(db, storage, scanner, settings).open_original(
        user_id=current_user.id, document_id=document_id
    )
    doc = result.document
    return StreamingResponse(
        _stream(result.stream),
        media_type="application/octet-stream",
        headers={
            **_NO_STORE,
            "Content-Disposition": _content_disposition("attachment", doc.original_filename),
            "Content-Length": str(doc.file_size),
        },
    )


@router.get("/{document_id}/inline")
async def inline_document(
    document_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
    storage: Storage,
    scanner: Scan,
    settings: AppSettings,
) -> StreamingResponse:
    """For the viewer only (D-72): PDFs and images, with a sandboxing CSP. Never HTML."""
    service = _service(db, storage, scanner, settings)
    doc = await service.get_owned(user_id=current_user.id, document_id=document_id)
    if doc.file_type not in _INLINE_TYPES:
        raise HTTPException(
            409,
            detail={
                "code": "INLINE_NOT_SUPPORTED",
                "message": "This document type cannot be shown inline.",
            },
        )
    result = await service.open_original(user_id=current_user.id, document_id=document_id)
    return StreamingResponse(
        _stream(result.stream),
        media_type=doc.mime_type,
        headers={
            **_NO_STORE,
            "Content-Disposition": _content_disposition("inline", doc.original_filename),
            "Content-Security-Policy": "sandbox; default-src 'none'",
            "Content-Length": str(doc.file_size),
        },
    )
