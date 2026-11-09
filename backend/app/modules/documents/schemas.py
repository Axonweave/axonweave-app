import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.documents.validation import sanitise_display_name

FileTypeLiteral = Literal["pdf", "pptx", "docx", "txt", "md", "png", "jpg"]
StatusLiteral = Literal[
    "uploaded",
    "queued",
    "validating",
    "extracting",
    "ocr_processing",
    "normalising",
    "chunking",
    "embedding",
    "indexing",
    "completed",
    "failed",
    "cancelled",
]


class DocumentOut(BaseModel):
    """Public document metadata. The storage key and checksum are never exposed."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    subject_id: uuid.UUID | None
    folder_id: uuid.UUID | None
    chapter_id: uuid.UUID | None
    display_name: str
    original_filename: str
    file_type: str
    mime_type: str
    file_size: int
    processing_status: str
    active_version: int | None
    latest_version: int
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class DocumentResponse(BaseModel):
    success: bool = True
    data: DocumentOut


class DocumentListResponse(BaseModel):
    success: bool = True
    data: list[DocumentOut]
    total: int
    limit: int
    offset: int


class RejectedFile(BaseModel):
    filename: str
    code: str
    message: str


class UploadData(BaseModel):
    documents: list[DocumentOut]
    rejected: list[RejectedFile]


class UploadResponse(BaseModel):
    success: bool = True
    data: UploadData


class Placement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: uuid.UUID
    subject_id: uuid.UUID | None = None
    folder_id: uuid.UUID | None = None
    chapter_id: uuid.UUID | None = None


class UpdateDocumentRequest(BaseModel):
    """Rename and/or move. A move sends the whole new placement."""

    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    placement: Placement | None = None

    @field_validator("display_name")
    @classmethod
    def _clean(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = sanitise_display_name(value)
        if not cleaned:
            raise ValueError("display_name is empty")
        return cleaned


class ProcessingStatusOut(BaseModel):
    document_id: uuid.UUID
    version: int
    processing_status: str
    stage: str | None
    job_status: str | None
    retry_count: int
    error_code: str | None
    updated_at: datetime


class ProcessingStatusResponse(BaseModel):
    success: bool = True
    data: ProcessingStatusOut


SortField = Literal["created_at", "updated_at", "display_name", "file_size"]


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: str
    stage: str
    retry_count: int
    error_code: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class ProcessingDetailsOut(BaseModel):
    document_id: uuid.UUID
    version: int
    processing_status: str
    extraction_method: str | None
    ocr_used: bool
    ocr_mean_confidence: float | None
    page_count: int | None
    slide_count: int | None
    word_count: int | None
    warnings: list[str]
    pipeline_version: str | None
    index_version: int | None
    chunk_count: int
    jobs: list[JobOut]


class ProcessingDetailsResponse(BaseModel):
    success: bool = True
    data: ProcessingDetailsOut


class PageOut(BaseModel):
    number: int
    kind: str  # "page" or "slide"
    chunk_count: int
    char_count: int


class PagesResponse(BaseModel):
    success: bool = True
    data: list[PageOut]


class ChunkOut(BaseModel):
    chunk_index: int
    text: str
    page_number: int | None
    slide_number: int | None
    section_heading: str | None
    token_count: int


class ContentResponse(BaseModel):
    success: bool = True
    data: list[ChunkOut]
    total: int
    limit: int
    offset: int
