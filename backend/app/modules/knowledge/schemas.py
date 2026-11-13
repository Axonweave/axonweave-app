import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

JobStatusLiteral = Literal[
    "pending",
    "retrieving_sources",
    "extracting",
    "validating",
    "saving",
    "completed",
    "failed",
    "cancelled",
]


class ExtractRequest(BaseModel):
    """Which document to extract concepts from. Ownership is verified in the service (a foreign id
    is a 404 exactly like a missing one); the client never supplies a user or workspace id."""

    model_config = ConfigDict(extra="forbid")

    document_id: uuid.UUID


class ExtractionJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    workspace_id: uuid.UUID
    status: JobStatusLiteral
    progress: int
    error_code: str | None
    error_message: str | None = None
    cancel_requested: bool
    extraction_version: str
    # Counts only (units, batches, nodes created, evidence added, dropped items). Never text.
    source_stats: dict[str, Any] | None
    result_stats: dict[str, Any] | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    # True when an identical request was already running and this is that job.
    existing: bool = False


class ExtractionJobResponse(BaseModel):
    success: bool = True
    data: ExtractionJobOut


class ExtractionJobListResponse(BaseModel):
    success: bool = True
    data: list[ExtractionJobOut]
    total: int
    limit: int
    offset: int
