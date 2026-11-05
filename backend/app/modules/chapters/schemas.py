import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

_VALID_STATUSES = ("not_started", "in_progress", "completed")


class ChapterOut(BaseModel):
    id: uuid.UUID
    subject_id: uuid.UUID
    folder_id: uuid.UUID | None
    title: str
    description: str | None
    display_order: int
    status: str
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChapterListResponse(BaseModel):
    success: bool = True
    data: list[ChapterOut]
    total: int
    limit: int
    offset: int


class ChapterResponse(BaseModel):
    success: bool = True
    data: ChapterOut


class CreateChapterRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=5000)
    folder_id: uuid.UUID | None = None
    # Omit to append after the subject's last chapter.
    display_order: int | None = Field(default=None, ge=0)
    status: Literal["not_started", "in_progress", "completed"] = "not_started"

    @field_validator("title")
    @classmethod
    def strip_title(cls, v: str) -> str:
        return v.strip()


class UpdateChapterRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=5000)
    folder_id: uuid.UUID | None = None
    folder_id_set: bool = False
    display_order: int | None = Field(default=None, ge=0)
    status: Literal["not_started", "in_progress", "completed"] | None = None

    @field_validator("title")
    @classmethod
    def strip_title(cls, v: str | None) -> str | None:
        return v.strip() if v is not None else v


class ReorderChaptersRequest(BaseModel):
    chapter_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
