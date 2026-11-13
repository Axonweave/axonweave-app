"""Schemas for the learner evidence APIs (Milestone 6.5). Responses never include question or
answer text, only ids, scores and metadata (spec 13.6: no unnecessary sensitive content)."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class SyncOut(BaseModel):
    ingested: int
    remapped: int
    more: bool


class SyncResponse(BaseModel):
    success: bool = True
    data: SyncOut


class EvidenceSummaryOut(BaseModel):
    total: int
    unmapped: int
    proposed_links: int


class EvidenceSummaryResponse(BaseModel):
    success: bool = True
    data: EvidenceSummaryOut


class LearnerEvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    knowledge_node_id: uuid.UUID | None
    source_type: str
    source_id: uuid.UUID
    source_event_id: uuid.UUID
    topic: str | None
    evidence_value: float
    evidence_metadata: dict[str, Any]
    occurred_at: datetime


class LearnerEvidenceListResponse(BaseModel):
    success: bool = True
    data: list[LearnerEvidenceOut]
    total: int
    limit: int
    offset: int


class ConceptLinkOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    source_type: str
    source_id: uuid.UUID
    knowledge_node_id: uuid.UUID
    node_name: str
    source_label: str | None
    method: str
    status: str
    created_at: datetime


class ConceptLinkResponse(BaseModel):
    success: bool = True
    data: ConceptLinkOut


class ConceptLinkListResponse(BaseModel):
    success: bool = True
    data: list[ConceptLinkOut]
    total: int
    limit: int
    offset: int


class ConceptStateOut(BaseModel):
    knowledge_node_id: uuid.UUID
    workspace_id: uuid.UUID | None
    node_name: str
    state: str
    mastery_estimate: float | None
    confidence: float
    evidence_count: int
    last_evidence_at: datetime | None
    next_review_at: datetime | None
    calculation_version: str
    explanation: str
    explanation_facts: dict[str, Any]


class ConceptStateResponse(BaseModel):
    success: bool = True
    data: ConceptStateOut


class ConceptStateListResponse(BaseModel):
    success: bool = True
    data: list[ConceptStateOut]
    total: int
    limit: int
    offset: int


class RecalculateOut(BaseModel):
    mode: str  # "queued" (worker will do it) or "done" (finished in this request)
    states: int | None = None


class RecalculateResponse(BaseModel):
    success: bool = True
    data: RecalculateOut
