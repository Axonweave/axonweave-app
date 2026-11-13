"""Schemas for the misconception APIs (Milestone 6.7)."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RelatedConceptOut(BaseModel):
    id: uuid.UUID
    name: str


class MisconceptionOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    knowledge_node_id: uuid.UUID
    node_name: str
    description: str
    explanation: str
    recommended_action: str | None
    confidence: float
    # below 0.7 the UI must word it as a possibility, never as a fact (spec 15.3)
    tentative: bool
    status: str
    evidence_count: int
    detection_version: str
    prompt_version: str
    related_concepts: list[RelatedConceptOut]
    edited_by_user: bool
    created_at: datetime
    updated_at: datetime
    dismissed_at: datetime | None


class MisconceptionResponse(BaseModel):
    success: bool = True
    data: MisconceptionOut


class MisconceptionListResponse(BaseModel):
    success: bool = True
    data: list[MisconceptionOut]
    total: int
    limit: int
    offset: int


class MisconceptionEvidenceOut(BaseModel):
    answer_id: uuid.UUID
    question_id: uuid.UUID
    question: str
    expected_answers: list[str]
    submitted_answer: Any
    submitted_at: datetime


class MisconceptionEvidenceResponse(BaseModel):
    success: bool = True
    data: list[MisconceptionEvidenceOut]


class DetectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: uuid.UUID


class DetectOut(BaseModel):
    # created | existing | none_found | insufficient_evidence
    outcome: str
    wrong_answers: int
    questions: int
    misconceptions: list[MisconceptionOut]


class DetectResponse(BaseModel):
    success: bool = True
    data: DetectOut


class MisconceptionPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str | None = Field(default=None, min_length=8, max_length=300)
    explanation: str | None = Field(default=None, min_length=8, max_length=900)
    recommended_action: str | None = Field(default=None, max_length=300)
