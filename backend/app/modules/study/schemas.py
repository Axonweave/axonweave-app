"""Study API schemas. Job and material responses never contain source text, prompts, provider
errors or storage details. (Answer keys, when quizzes arrive in M3, never appear here either.)"""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.study.schemas import GenerationRequest

__all__ = [
    "GenerationJobListResponse",
    "GenerationJobOut",
    "GenerationJobResponse",
    "GenerationRequest",
    "GeneratorListResponse",
    "GeneratorOut",
    "StudyMaterialOut",
    "StudyMaterialResponse",
    "EditMaterialRequest",
    "RestoreRequest",
    "RegenerateRequest",
    "VersionListResponse",
    "VersionOut",
    "VersionResponse",
    "PreviewOut",
    "PreviewResponse",
]

JobStatusLiteral = Literal[
    "pending",
    "retrieving_sources",
    "generating",
    "validating",
    "saving",
    "completed",
    "failed",
    "cancelled",
]


class GenerationJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    generation_type: str
    status: JobStatusLiteral
    progress: int
    error_code: str | None
    error_message: str | None = None
    study_material_id: uuid.UUID | None
    cancel_requested: bool
    # Counts only (documents, chunks included, truncated...). Never text.
    source_stats: dict[str, Any] | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    # True when an identical request was already running and this is that job.
    existing: bool = False


class GenerationJobResponse(BaseModel):
    success: bool = True
    data: GenerationJobOut


class GenerationJobListResponse(BaseModel):
    success: bool = True
    data: list[GenerationJobOut]
    total: int
    limit: int
    offset: int


class StudyMaterialOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    subject_id: uuid.UUID | None
    chapter_id: uuid.UUID | None
    title: str
    resource_type: str
    status: str
    content: dict[str, Any]
    generation_settings: dict[str, Any]
    source_metadata: dict[str, Any]
    current_version: int
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None
    # Source documents deleted after generation: the material stays, references are unavailable.
    unavailable_document_ids: list[uuid.UUID] = Field(default_factory=list)
    # The flashcard deck or quiz row that holds this material's live items (decks, quizzes, banks).
    # The UI needs it to reach /study/flashcards/{id} and /study/quizzes/{id}.
    item_id: uuid.UUID | None = None


class StudyMaterialResponse(BaseModel):
    success: bool = True
    data: StudyMaterialOut


class GeneratorOut(BaseModel):
    key: str
    resource_type: str
    settings_schema: dict[str, Any]


class GeneratorListResponse(BaseModel):
    success: bool = True
    data: list[GeneratorOut]


class EditMaterialRequest(BaseModel):
    """`expected_version` is the version the user was looking at; a different current version is a
    409, so an edit never silently replaces a newer one (another tab, an applied regeneration)."""

    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    payload: dict[str, Any]


class RestoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    version: int = Field(ge=1)


class RegenerateRequest(BaseModel):
    """Regenerate the whole material, or only the section at `section_index`. The result is a
    preview job; nothing changes until the preview is applied."""

    model_config = ConfigDict(extra="forbid")

    section_index: int | None = Field(default=None, ge=0, le=200)
    settings: dict[str, Any] | None = None


class VersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    version_number: int
    origin: str
    created_at: datetime
    content: dict[str, Any] | None = None


class VersionListResponse(BaseModel):
    success: bool = True
    data: list[VersionOut]


class VersionResponse(BaseModel):
    success: bool = True
    data: VersionOut


class PreviewOut(BaseModel):
    material_id: uuid.UUID
    base_version: int
    current_version: int
    stale: bool
    section_index: int | None
    content: dict[str, Any]


class PreviewResponse(BaseModel):
    success: bool = True
    data: PreviewOut
