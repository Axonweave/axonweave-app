"""Schemas for research projects (Phase 7 M7.1). Free text is trimmed and length-capped; the short
lists are capped in size and per item and cleaned of blanks and duplicates."""

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

StatusLiteral = Literal["planning", "active", "on_hold", "completed"]
SortLiteral = Literal["updated_at", "created_at", "title", "target_date"]

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=200)]
Domain = Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)]
LongText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)]


def _clean(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in items:
        item = " ".join(raw.split())
        if item and item.lower() not in seen:
            seen.add(item.lower())
            out.append(item)
    return out


Objectives = Annotated[
    list[Annotated[str, StringConstraints(max_length=500)]],
    Field(max_length=20),
    AfterValidator(_clean),
]
Keywords = Annotated[
    list[Annotated[str, StringConstraints(max_length=60)]],
    Field(max_length=20),
    AfterValidator(_clean),
]


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: uuid.UUID
    title: Title
    description: LongText | None = None
    domain: Domain | None = None
    research_problem: LongText | None = None
    objectives: Objectives = Field(default_factory=list)
    research_questions: Objectives = Field(default_factory=list)
    keywords: Keywords = Field(default_factory=list)
    status: StatusLiteral = "planning"
    start_date: date | None = None
    target_date: date | None = None

    @model_validator(mode="after")
    def _dates(self) -> "ProjectCreate":
        if self.start_date and self.target_date and self.target_date < self.start_date:
            raise ValueError("target_date cannot be before start_date")
        return self


class ProjectPatch(BaseModel):
    """Only the fields sent are changed. `null` clears an optional field."""

    model_config = ConfigDict(extra="forbid")

    title: Title | None = None
    description: LongText | None = None
    domain: Domain | None = None
    research_problem: LongText | None = None
    objectives: Objectives | None = None
    research_questions: Objectives | None = None
    keywords: Keywords | None = None
    status: StatusLiteral | None = None
    start_date: date | None = None
    target_date: date | None = None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    title: str
    description: str | None
    domain: str | None
    research_problem: str | None
    objectives: list[str]
    research_questions: list[str]
    keywords: list[str]
    status: str
    start_date: date | None
    target_date: date | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ProjectResponse(BaseModel):
    success: bool = True
    data: ProjectOut


class ProjectListResponse(BaseModel):
    success: bool = True
    data: list[ProjectOut]
    total: int
    limit: int
    offset: int
