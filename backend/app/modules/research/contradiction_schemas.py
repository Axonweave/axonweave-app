"""Schemas for contradictions (Phase 7 M7.7). Names carry the `ResearchContradiction` prefix to stay
unique across the OpenAPI document."""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

Category = Literal["genuine", "context_dependent", "metric_incompatible", "insufficient_evidence"]
Review = Literal["unreviewed", "genuine", "context_dependent", "dismissed"]
Explanation = Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)]


class ResearchContradictionGenerate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paper_ids: list[uuid.UUID] | None = None


class ResearchContradictionPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_status: Review | None = None
    researcher_explanation: Explanation | None = None


class ResearchContradictionSide(BaseModel):
    paper_id: uuid.UUID
    paper_title: str
    claim_type: str
    claim_text: str
    evidence_id: uuid.UUID | None
    quote: str | None
    page_number: int | None


class ResearchContradictionOut(BaseModel):
    id: uuid.UUID
    research_project_id: uuid.UUID
    claim_a: ResearchContradictionSide
    claim_b: ResearchContradictionSide
    conditions: dict[str, Any]
    category: str
    explanation: str
    confidence_label: str
    review_status: str
    researcher_explanation: str | None
    analysis_version: str
    created_at: datetime
    updated_at: datetime


class ResearchContradictionResponse(BaseModel):
    success: bool = True
    data: ResearchContradictionOut


class ResearchContradictionListResponse(BaseModel):
    success: bool = True
    data: list[ResearchContradictionOut]
    total: int
    limit: int
    offset: int
