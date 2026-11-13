"""Schemas for concept links (Phase 7 M7.10). Names carry the `ResearchConcept` prefix to stay
unique across the OpenAPI document."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

LinkStatus = Literal["suggested", "confirmed", "rejected"]


class ResearchConceptSuggest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paper_ids: list[uuid.UUID] | None = Field(default=None, max_length=100)


class ResearchConceptLinkPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    link_status: LinkStatus


class ResearchConceptPaperRef(BaseModel):
    id: uuid.UUID
    title: str


class ResearchConceptNodeRef(BaseModel):
    id: uuid.UUID
    name: str
    node_type: str


class ResearchConceptLinkOut(BaseModel):
    id: uuid.UUID
    research_project_id: uuid.UUID
    paper: ResearchConceptPaperRef
    node: ResearchConceptNodeRef
    match_kind: str
    matched_text: str
    link_status: str
    claim_type: str
    claim_text: str
    evidence_id: uuid.UUID | None
    document_id: uuid.UUID | None
    page_number: int | None
    mention_count: int
    created_at: datetime


class ResearchConceptLinkResponse(BaseModel):
    success: bool = True
    data: ResearchConceptLinkOut


class ResearchConceptLinkListResponse(BaseModel):
    success: bool = True
    data: list[ResearchConceptLinkOut]
    total: int
    limit: int
    offset: int


class ResearchConceptClaim(BaseModel):
    paper_id: uuid.UUID
    paper_title: str
    claim_text: str
    quote: str | None
    page_number: int | None


class ResearchConceptPaper(BaseModel):
    link_id: uuid.UUID
    paper_id: uuid.UUID
    paper_title: str
    research_project_id: uuid.UUID
    project_title: str
    link_status: str
    matched_text: str


class ResearchConceptGap(BaseModel):
    id: uuid.UUID
    research_project_id: uuid.UUID
    title: str
    category: str
    confidence_label: str
    validation_status: str


class ResearchConceptResearchOut(BaseModel):
    """Research connected to one concept. Papers show suggested and confirmed links (with their
    status); the findings, methods, datasets, metrics and gaps come from confirmed links only."""

    node: ResearchConceptNodeRef
    papers: list[ResearchConceptPaper]
    findings: list[ResearchConceptClaim]
    methods: list[ResearchConceptClaim]
    datasets: list[ResearchConceptClaim]
    metrics: list[ResearchConceptClaim]
    gaps: list[ResearchConceptGap]


class ResearchConceptResearchResponse(BaseModel):
    success: bool = True
    data: ResearchConceptResearchOut
