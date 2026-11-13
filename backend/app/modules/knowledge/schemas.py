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
    # A document run has `document_id`; a web run has `subject_id` and `topic` (D-144).
    document_id: uuid.UUID | None
    source_kind: Literal["document", "web"] = "document"
    subject_id: uuid.UUID | None = None
    topic: str | None = None
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


class ExtractSubjectRequest(BaseModel):
    """Extract every ready document of one subject (a foreign subject is a 404)."""

    model_config = ConfigDict(extra="forbid")

    subject_id: uuid.UUID


class ExtractWebRequest(BaseModel):
    """Build a subject's graph from a web search on its name (a foreign subject is a 404)."""

    model_config = ConfigDict(extra="forbid")

    subject_id: uuid.UUID


class SubjectRunOut(BaseModel):
    ready: int
    skipped: int
    queued: int
    already_running: int
    not_ready: int
    over_cap: int
    job_ids: list[uuid.UUID]


class SubjectRunResponse(BaseModel):
    success: bool = True
    data: SubjectRunOut


class ExtractionJobResponse(BaseModel):
    success: bool = True
    data: ExtractionJobOut


class ExtractionJobListResponse(BaseModel):
    success: bool = True
    data: list[ExtractionJobOut]
    total: int
    limit: int
    offset: int
