"""Schemas for paper comparisons (Phase 7 M7.4). Names carry the `ResearchComparison` prefix so they
stay unique across the OpenAPI document."""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)

from app.research.comparison import MAX_PAPERS, MIN_PAPERS

DimensionLiteral = Literal[
    "research_problem",
    "objectives",
    "methodology",
    "models",
    "dataset",
    "sample_size",
    "metrics",
    "setup",
    "results",
    "contributions",
    "limitations",
    "future_work",
]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
NoteText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=5000)]


def _unique(items: list[uuid.UUID]) -> list[uuid.UUID]:
    if len(set(items)) != len(items):
        raise ValueError("Choose each paper only once.")
    return items


class ResearchComparisonCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Title
    paper_ids: Annotated[
        list[uuid.UUID],
        Field(min_length=MIN_PAPERS, max_length=MAX_PAPERS),
        AfterValidator(_unique),
    ]
    # None = every dimension.
    dimensions: Annotated[list[DimensionLiteral], Field(min_length=1, max_length=12)] | None = None

    @field_validator("dimensions")
    @classmethod
    def _dedupe(cls, v: list[str] | None) -> list[str] | None:
        return None if v is None else list(dict.fromkeys(v))


class ResearchComparisonPatch(BaseModel):
    """Only the title and the researcher's own notes can change; extracted claims never do."""

    model_config = ConfigDict(extra="forbid")

    title: Title | None = None
    notes: dict[DimensionLiteral, NoteText] | None = None


class ResearchComparisonSummary(BaseModel):
    id: uuid.UUID
    research_project_id: uuid.UUID
    title: str
    paper_count: int
    created_at: datetime
    updated_at: datetime


class ResearchComparisonOut(BaseModel):
    id: uuid.UUID
    research_project_id: uuid.UUID
    title: str
    paper_ids: list[uuid.UUID]
    configuration: dict[str, Any]
    result: dict[str, Any]
    notes: dict[str, str]
    created_at: datetime
    updated_at: datetime


class ResearchComparisonResponse(BaseModel):
    success: bool = True
    data: ResearchComparisonOut


class ResearchComparisonListResponse(BaseModel):
    success: bool = True
    data: list[ResearchComparisonSummary]
    total: int
    limit: int
    offset: int
