import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

_COLOUR_RE = r"^#[0-9A-Fa-f]{6}$"


class FolderOut(BaseModel):
    id: uuid.UUID
    subject_id: uuid.UUID
    parent_folder_id: uuid.UUID | None
    name: str
    description: str | None
    display_order: int
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FolderListResponse(BaseModel):
    success: bool = True
    data: list[FolderOut]


class FolderResponse(BaseModel):
    success: bool = True
    data: FolderOut


class CreateFolderRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    parent_folder_id: uuid.UUID | None = None
    display_order: int = Field(default=0, ge=0)

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return v.strip()


class UpdateFolderRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    display_order: int | None = Field(default=None, ge=0)

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str | None) -> str | None:
        return v.strip() if v is not None else v
