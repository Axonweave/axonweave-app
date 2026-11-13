"""Schemas for paper analysis and notes (Phase 7 M7.3). Names are prefixed `Paper...` so they stay
unique across the OpenAPI document (the generated frontend types rely on it)."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

SectionLiteral = Literal[
    "research_problem",
    "objectives",
    "methodology",
    "dataset",
    "evaluation",
    "results",
    "contributions",
    "limitations",
    "future_work",
    "references",
]
AnalysisStatusLiteral = Literal[
    "pending",
    "retrieving_sources",
    "extracting",
    "validating",
    "saving",
    "completed",
    "failed",
    "cancelled",
]


class PaperAnalysisRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    research_paper_id: uuid.UUID
    version_number: int
    status: AnalysisStatusLiteral
    progress: int
    extraction_version: str
    prompt_version: str | None
    model_identifier: str | None
    error_code: str | None
    error_message: str | None = None
    result_stats: dict[str, object] | None
    existing: bool = False
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class PaperAnalysisRunResponse(BaseModel):
    success: bool = True
    data: PaperAnalysisRunOut


class PaperAnalysisRunListResponse(BaseModel):
    success: bool = True
    data: list[PaperAnalysisRunOut]
    total: int
    limit: int
    offset: int


class PaperEvidenceOut(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID | None
    chunk_id: uuid.UUID | None
    page_number: int | None
    quote: str


class PaperClaimOut(BaseModel):
    index: int
    label: str | None
    text: str
    origin: Literal["reported", "ai_inferred"]
    confidence: float | None
    evidence: list[PaperEvidenceOut]


class PaperSectionOut(BaseModel):
    section: SectionLiteral
    # Empty = "Not reported in the available paper." (never filled with guesses).
    items: list[PaperClaimOut]


class PaperAnalysisOut(BaseModel):
    """The analysis a reader sees: the requested (or latest completed) run with every section,
    plus the run in progress, if any."""

    run: PaperAnalysisRunOut | None
    active: PaperAnalysisRunOut | None
    sections: list[PaperSectionOut]


class PaperAnalysisResponse(BaseModel):
    success: bool = True
    data: PaperAnalysisOut


NoteBody = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)]


class PaperNoteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section: SectionLiteral | None = None
    body: NoteBody


class PaperNotePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: NoteBody


class PaperNoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    research_paper_id: uuid.UUID
    section: SectionLiteral | None
    body: str
    created_at: datetime
    updated_at: datetime


class PaperNoteResponse(BaseModel):
    success: bool = True
    data: PaperNoteOut


class PaperNoteListResponse(BaseModel):
    success: bool = True
    data: list[PaperNoteOut]
