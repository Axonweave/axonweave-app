"""Schemas for evidence matrices (Phase 7 M7.5). Names carry the `ResearchMatrix` prefix to stay
unique across the OpenAPI document."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
ColumnTitle = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
CellValue = Annotated[str, StringConstraints(strip_whitespace=True, max_length=5000)]
Origin = Literal["extracted", "ai_generated", "researcher"]


def _unique(items: list[uuid.UUID]) -> list[uuid.UUID]:
    if len(set(items)) != len(items):
        raise ValueError("List each item only once.")
    return items


UniqueIds = Annotated[list[uuid.UUID], Field(max_length=60), AfterValidator(_unique)]


class ResearchMatrixCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Title
    description: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] | None
    ) = None
    paper_ids: UniqueIds = Field(default_factory=list)


class ResearchMatrixPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Title | None = None
    description: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] | None
    ) = None


class ResearchMatrixAddPapers(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paper_ids: Annotated[UniqueIds, Field(min_length=1)]


class ResearchMatrixColumnCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: ColumnTitle


class ResearchMatrixColumnPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: ColumnTitle


class ResearchMatrixColumnOrder(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column_ids: UniqueIds


class ResearchMatrixEntryPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: CellValue


class ResearchMatrixColumnOut(BaseModel):
    id: uuid.UUID
    column_key: str
    title: str
    position: int
    is_default: bool


class ResearchMatrixEvidenceOut(BaseModel):
    id: uuid.UUID
    quote: str
    page_number: int | None
    document_id: uuid.UUID | None


class ResearchMatrixCellOut(BaseModel):
    column_id: uuid.UUID
    value: str
    origin: Origin
    evidence: list[ResearchMatrixEvidenceOut]
    stale_evidence: int  # linked evidence rows that no longer exist


class ResearchMatrixPaperOut(BaseModel):
    id: uuid.UUID
    title: str
    authors: list[str]
    publication_year: int | None


class ResearchMatrixRowOut(BaseModel):
    paper: ResearchMatrixPaperOut
    cells: list[ResearchMatrixCellOut]


class ResearchMatrixOut(BaseModel):
    id: uuid.UUID
    research_project_id: uuid.UUID
    title: str
    description: str | None
    columns: list[ResearchMatrixColumnOut]
    rows: list[ResearchMatrixRowOut]
    created_at: datetime
    updated_at: datetime


class ResearchMatrixSummary(BaseModel):
    id: uuid.UUID
    research_project_id: uuid.UUID
    title: str
    description: str | None
    paper_count: int
    updated_at: datetime


class ResearchMatrixResponse(BaseModel):
    success: bool = True
    data: ResearchMatrixOut


class ResearchMatrixListResponse(BaseModel):
    success: bool = True
    data: list[ResearchMatrixSummary]
    total: int
    limit: int
    offset: int
