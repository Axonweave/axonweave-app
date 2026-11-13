"""Schemas for the paper library (Phase 7 M7.2). The client can only supply user-entered metadata:
provenance values other than `user_supplied` are set by the server when extraction or a metadata
provider fills a field (later milestones)."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)

from app.research.papers import InvalidDoiError, normalise_doi

PaperStatusLiteral = Literal["unread", "reading", "read"]
PaperSortLiteral = Literal["updated_at", "created_at", "title", "publication_year"]

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=500)]
Short = Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)]
Tiny = Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)]
Abstract = Annotated[str, StringConstraints(strip_whitespace=True, max_length=10000)]


def _clean(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in items:
        item = " ".join(raw.split())
        if item and item.lower() not in seen:
            seen.add(item.lower())
            out.append(item)
    return out


Authors = Annotated[
    list[Annotated[str, StringConstraints(max_length=200)]],
    Field(max_length=100),
    AfterValidator(_clean),
]
Keywords = Annotated[
    list[Annotated[str, StringConstraints(max_length=60)]],
    Field(max_length=30),
    AfterValidator(_clean),
]


class _PaperFields(BaseModel):
    """Shared validation. Blank strings become None."""

    @field_validator("doi", check_fields=False)
    @classmethod
    def _doi(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        try:
            return normalise_doi(v)
        except InvalidDoiError as exc:
            raise ValueError("DOI must look like 10.1234/abc") from exc

    @field_validator("url", check_fields=False)
    @classmethod
    def _url(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        v = v.strip()
        if len(v) > 1000 or not v.lower().startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v


class PaperCreate(_PaperFields):
    model_config = ConfigDict(extra="forbid")

    title: Title
    abstract: Abstract | None = None
    authors: Authors = Field(default_factory=list)
    publication_year: int | None = Field(default=None, ge=1000, le=2200)
    venue: Short | None = None
    publisher: Short | None = None
    doi: str | None = None
    url: str | None = None
    keywords: Keywords = Field(default_factory=list)
    volume: Tiny | None = None
    issue: Tiny | None = None
    pages: Tiny | None = None
    status: PaperStatusLiteral = "unread"
    # An existing document of the user (PDF uploads go through the ordinary document upload first).
    document_id: uuid.UUID | None = None


class PaperPatch(_PaperFields):
    """Only the fields sent are changed. `null` clears an optional field."""

    model_config = ConfigDict(extra="forbid")

    title: Title | None = None
    abstract: Abstract | None = None
    authors: Authors | None = None
    publication_year: int | None = Field(default=None, ge=1000, le=2200)
    venue: Short | None = None
    publisher: Short | None = None
    doi: str | None = None
    url: str | None = None
    keywords: Keywords | None = None
    volume: Tiny | None = None
    issue: Tiny | None = None
    pages: Tiny | None = None
    status: PaperStatusLiteral | None = None
    metadata_verified: bool | None = None
    document_id: uuid.UUID | None = None


class PaperOut(BaseModel):
    id: uuid.UUID
    research_project_id: uuid.UUID
    document_id: uuid.UUID | None
    document_name: str | None
    processing_status: str | None  # the linked document's Phase 3 status; None without a file
    analysis_status: str
    title: str
    abstract: str | None
    authors: list[str]
    publication_year: int | None
    venue: str | None
    publisher: str | None
    doi: str | None
    url: str | None
    keywords: list[str]
    volume: str | None
    issue: str | None
    pages: str | None
    metadata_source: str
    metadata_verified: bool
    status: str
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PaperResponse(BaseModel):
    success: bool = True
    data: PaperOut


class PaperListResponse(BaseModel):
    success: bool = True
    data: list[PaperOut]
    total: int
    limit: int
    offset: int


class DuplicatePaperOut(BaseModel):
    id: uuid.UUID
    title: str
    authors: list[str]
    publication_year: int | None
    doi: str | None
    has_file: bool


class DuplicateCandidateOut(BaseModel):
    paper_a: DuplicatePaperOut
    paper_b: DuplicatePaperOut
    reason: str
    score: float
    shared_authors: list[str]
    same_year: bool


class DuplicateListResponse(BaseModel):
    success: bool = True
    data: list[DuplicateCandidateOut]


class DuplicateResolve(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paper_id: uuid.UUID
    other_id: uuid.UUID
    action: Literal["not_duplicate", "merge"]
    # for merge: which of the two stays. The other is removed after its blank fields are copied.
    survivor_id: uuid.UUID | None = None


class DuplicateResolveOut(BaseModel):
    action: str
    survivor: PaperOut | None = None


class DuplicateResolveResponse(BaseModel):
    success: bool = True
    data: DuplicateResolveOut
