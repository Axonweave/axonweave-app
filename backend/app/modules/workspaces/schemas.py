"""Pydantic schemas for workspaces module (B2)."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, field_validator

WorkspaceType = Literal[
    "university", "personal_learning", "research", "professional_development", "custom"
]


class WorkspaceOut(BaseModel):
    id: UUID
    name: str
    description: str | None
    workspace_type: str
    icon: str | None
    colour: str | None
    is_default: bool
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WorkspaceListResponse(BaseModel):
    success: bool = True
    data: list[WorkspaceOut]
    total: int


class WorkspaceResponse(BaseModel):
    success: bool = True
    data: WorkspaceOut


class CreateWorkspaceRequest(BaseModel):
    name: str
    description: str | None = None
    workspace_type: WorkspaceType = "personal_learning"
    icon: str | None = None
    colour: str | None = None

    @field_validator("name")
    @classmethod
    def _name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Workspace name cannot be empty.")
        if len(v) > 255:
            raise ValueError("Workspace name must be 255 characters or fewer.")
        return v

    @field_validator("colour")
    @classmethod
    def _valid_colour(cls, v: str | None) -> str | None:
        if v is not None and not v.startswith("#"):
            raise ValueError("Colour must be a hex colour code (e.g. #3b82f6).")
        return v


class UpdateWorkspaceRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    workspace_type: WorkspaceType | None = None
    icon: str | None = None
    colour: str | None = None

    @field_validator("name")
    @classmethod
    def _name_not_empty(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("Workspace name cannot be empty.")
            if len(v) > 255:
                raise ValueError("Workspace name must be 255 characters or fewer.")
        return v
