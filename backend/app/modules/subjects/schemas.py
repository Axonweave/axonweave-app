import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class SubjectOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    description: str | None
    colour: str | None
    icon: str | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SubjectListResponse(BaseModel):
    success: bool = True
    data: list[SubjectOut]
    total: int
    limit: int
    offset: int


class SubjectResponse(BaseModel):
    success: bool = True
    data: SubjectOut


_COLOUR_RE = r"^#[0-9A-Fa-f]{6}$"
_ICON_MAX = 64


class CreateSubjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    colour: str | None = Field(default=None, pattern=_COLOUR_RE)
    icon: str | None = Field(default=None, max_length=_ICON_MAX)

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return v.strip()


class UpdateSubjectRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    colour: str | None = Field(default=None, pattern=_COLOUR_RE)
    icon: str | None = Field(default=None, max_length=_ICON_MAX)

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str | None) -> str | None:
        return v.strip() if v is not None else v
