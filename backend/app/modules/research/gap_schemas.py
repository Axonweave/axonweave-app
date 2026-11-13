"""Schemas for research gaps (Phase 7 M7.6). Names carry the `ResearchGap` prefix to stay unique
across the OpenAPI document."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

Category = Literal[
    "methodological",
    "dataset",
    "population",
    "evaluation",
    "domain",
    "application",
    "generalisation",
    "reproducibility",
    "contradictory_findings",
]
Status = Literal["suggested", "accepted", "rejected", "investigating"]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Notes = Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)]


class ResearchGapGenerate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paper_ids: list[uuid.UUID] | None = None


class ResearchGapPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Title | None = None
    description: Text | None = None
    suggested_direction: Text | None = None
    validation_status: Status | None = None
    researcher_notes: Notes | None = None


class ResearchGapEvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    research_paper_id: uuid.UUID
    research_evidence_id: uuid.UUID | None
    evidence_role: str
    claim_type: str
    claim_text: str


class ResearchGapOut(BaseModel):
    id: uuid.UUID
    research_project_id: uuid.UUID
    title: str
    description: str
    category: str
    rationale: str
    confidence_label: str
    limitations: str
    suggested_direction: str
    validation_status: str
    analysis_version: str
    edited_by_user: bool
    researcher_notes: str | None
    created_at: datetime
    updated_at: datetime
    evidence: list[ResearchGapEvidenceOut]


class ResearchGapResponse(BaseModel):
    success: bool = True
    data: ResearchGapOut


class ResearchGapListResponse(BaseModel):
    success: bool = True
    data: list[ResearchGapOut]
    total: int
    limit: int
    offset: int
