"""Schemas for drafts and writing assistance (Phase 7 M7.9). Names carry the `ResearchDraft` /
`ResearchWriting` prefix to stay unique across the OpenAPI document."""

import uuid
from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

DocType = Literal["research_paper", "literature_review", "proposal", "report", "notes"]
DraftStatus = Literal["draft", "in_review", "final"]
Style = Literal["apa", "ieee", "mla", "chicago", "harvard"]
ChangeSource = Literal["manual", "ai_suggestion"]
Action = Literal[
    "draft_section",
    "expand",
    "synthesis",
    "rewrite",
    "tone",
    "grammar",
    "clarity",
    "organise",
]
Section = Literal[
    "abstract",
    "introduction",
    "background",
    "literature_review",
    "problem_statement",
    "objectives",
    "research_questions",
    "methodology",
    "proposed_approach",
    "results",
    "discussion",
    "limitations",
    "conclusion",
    "future_work",
]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Content = Annotated[str, StringConstraints(max_length=200_000)]


class ResearchDraftCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Title
    document_type: DocType = "research_paper"
    content: Content = ""
    citation_style: Style = "apa"


class ResearchDraftPatch(BaseModel):
    """Changing the title or content needs `expected_version`, the version the researcher was
    editing; a different current version is a 409 so nothing is overwritten silently."""

    model_config = ConfigDict(extra="forbid")

    title: Title | None = None
    content: Content | None = None
    document_type: DocType | None = None
    status: DraftStatus | None = None
    citation_style: Style | None = None
    expected_version: int | None = Field(default=None, ge=1)
    change_source: ChangeSource = "manual"
    change_summary: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] | None
    ) = None

    @model_validator(mode="after")
    def _needs_version(self) -> Self:
        if (self.title is not None or self.content is not None) and self.expected_version is None:
            raise ValueError("expected_version is required when the title or content changes")
        return self


class ResearchDraftRestore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)


class ResearchDraftSummary(BaseModel):
    id: uuid.UUID
    research_project_id: uuid.UUID
    title: str
    document_type: str
    status: str
    citation_style: str
    version_number: int
    word_count: int
    created_at: datetime
    updated_at: datetime


class ResearchDraftOut(ResearchDraftSummary):
    content: str


class ResearchDraftVersionSummary(BaseModel):
    version_number: int
    title: str
    change_summary: str
    change_source: str
    characters: int
    created_at: datetime


class ResearchDraftVersionOut(ResearchDraftVersionSummary):
    content: str


class ResearchDraftResponse(BaseModel):
    success: bool = True
    data: ResearchDraftOut


class ResearchDraftListResponse(BaseModel):
    success: bool = True
    data: list[ResearchDraftSummary]
    total: int
    limit: int
    offset: int


class ResearchDraftVersionListResponse(BaseModel):
    success: bool = True
    data: list[ResearchDraftVersionSummary]


class ResearchDraftVersionResponse(BaseModel):
    success: bool = True
    data: ResearchDraftVersionOut


class ResearchDraftSentenceCheck(BaseModel):
    text: str
    status: str
    paper_ids: list[uuid.UUID]


class ResearchDraftCheckOut(BaseModel):
    checks: list[ResearchDraftSentenceCheck]
    summary: dict[str, int]
    invalid_references: list[uuid.UUID]


class ResearchDraftCheckResponse(BaseModel):
    success: bool = True
    data: ResearchDraftCheckOut


class ResearchDraftExportOut(BaseModel):
    format: str
    filename: str
    content: str
    cited_count: int
    invalid_references: list[uuid.UUID]


class ResearchDraftExportResponse(BaseModel):
    success: bool = True
    data: ResearchDraftExportOut


class ResearchWritingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Action
    section: Section | None = None
    instruction: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)] = ""
    selected_text: Annotated[str, StringConstraints(max_length=8000)] = ""
    paper_ids: list[uuid.UUID] | None = Field(default=None, max_length=8)


class ResearchWritingSource(BaseModel):
    paper_id: uuid.UUID
    paper_title: str
    section: str
    claim_text: str
    quote: str | None


class ResearchWritingOut(BaseModel):
    action: str
    text: str
    notes: str
    sources: list[ResearchWritingSource]
    invalid_markers: int
    checks: list[ResearchDraftSentenceCheck]
    summary: dict[str, int]
    unsupported_count: int


class ResearchWritingResponse(BaseModel):
    success: bool = True
    data: ResearchWritingOut
