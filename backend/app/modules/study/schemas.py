"""Study API schemas. Job and material responses never contain source text, prompts, provider
errors or storage details. (Answer keys, when quizzes arrive in M3, never appear here either.)"""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

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
