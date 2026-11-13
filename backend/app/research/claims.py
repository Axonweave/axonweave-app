"""Verified claims of analysed papers, as plain data for the deterministic research tools (gaps,
contradictions). Loaded from the stored analyses (M7.3); nothing here calls a model."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass(frozen=True)
class StoredClaim:
    paper_id: uuid.UUID
    section: str
    index: int
    label: str | None
    text: str
    origin: str  # reported | ai_inferred
    evidence_id: uuid.UUID | None
    quote: str | None
    page_number: int | None
    document_id: uuid.UUID | None


@dataclass
class LoadedPaper:
    paper_id: uuid.UUID
    title: str
    year: int | None
    extraction_id: uuid.UUID
    version_number: int
    claims: list[StoredClaim] = field(default_factory=list)

    def in_section(self, *sections: str) -> list[StoredClaim]:
        return [c for c in self.claims if c.section in sections]
