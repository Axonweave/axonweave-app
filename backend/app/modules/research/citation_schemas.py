"""Schemas for citations (Phase 7 M7.8). Names carry the `ResearchCitation` prefix to stay unique
across the OpenAPI document."""

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Style = Literal["apa", "ieee", "mla", "chicago", "harvard"]
ExportFormat = Literal["text", "bibtex"]


class ResearchCitationGenerate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    style: Style
    paper_ids: list[uuid.UUID] | None = Field(default=None, max_length=100)
    accessed_date: date | None = None


class ResearchCitationIssue(BaseModel):
    field: str
    severity: str
    code: str
    message: str


class ResearchCitationOut(BaseModel):
    id: uuid.UUID
    research_project_id: uuid.UUID
    research_paper_id: uuid.UUID
    paper_title: str
    citation_style: str
    formatted_citation: str
    in_text_citation: str
    metadata: dict[str, Any]
    issues: list[ResearchCitationIssue]
    complete: bool
    metadata_changed: bool
    created_at: datetime
    updated_at: datetime


class ResearchCitationResponse(BaseModel):
    success: bool = True
    data: ResearchCitationOut


class ResearchCitationListResponse(BaseModel):
    success: bool = True
    data: list[ResearchCitationOut]
    total: int


class ResearchBibliographyOut(BaseModel):
    style: str
    format: str
    filename: str
    count: int
    content: str


class ResearchBibliographyResponse(BaseModel):
    success: bool = True
    data: ResearchBibliographyOut
