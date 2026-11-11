"""Schemas for the study library and exports. List items carry no content (no payload, no keys)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

ExportFormat = Literal["pdf", "csv", "md", "docx"]


class LibraryItemOut(BaseModel):
    id: uuid.UUID
    title: str
    resource_type: str
    status: str
    workspace_id: uuid.UUID
    subject_id: uuid.UUID | None
    chapter_id: uuid.UUID | None
    current_version: int
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None
    source_document_count: int
    # Source documents that were deleted later: the material stays, its references are unavailable.
    unavailable_source_count: int


class LibraryListResponse(BaseModel):
    success: bool = True
    data: list[LibraryItemOut]
    total: int
    limit: int
    offset: int


class ExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: ExportFormat


class ExportOut(BaseModel):
    id: uuid.UUID
    study_material_id: uuid.UUID
    format: ExportFormat
    status: str
    size_bytes: int | None
    error_code: str | None
    expires_at: datetime | None
    created_at: datetime
    download_path: str | None = None


class ExportResponse(BaseModel):
    success: bool = True
    data: ExportOut
