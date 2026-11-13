"""Paper metadata helpers (Phase 7 M7.2): DOI and title normalisation and duplicate candidates.
Pure functions. Duplicate detection only suggests: it never merges anything by itself, and similar
titles alone are never treated as the same paper (spec 24.4)."""

from __future__ import annotations

import re
import unicodedata
import uuid
from dataclasses import dataclass

_DOI = re.compile(r"^10\.\d{4,9}/\S+$")
_DOI_PREFIX = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.IGNORECASE)
_WORD = re.compile(r"[^\W_]+", re.UNICODE)
_STOP = frozenset("a an the of on in for and to with by from at is are as".split())

SIMILARITY_MIN = 0.8


class InvalidDoiError(ValueError):
    pass


def normalise_doi(value: str) -> str:
    """`https://doi.org/10.1000/ABC` and `doi:10.1000/abc` both become `10.1000/abc`."""
    text = _DOI_PREFIX.sub("", value.strip()).strip().rstrip(".,;").lower()
    if not _DOI.match(text) or len(text) > 200:
        raise InvalidDoiError("Not a valid DOI")
    return text


def doi_url(doi: str) -> str:
    return f"https://doi.org/{doi}"


def normalise_title(title: str) -> str:
    folded = unicodedata.normalize("NFKC", title).casefold()
    return " ".join(_WORD.findall(folded))[:500]


def _tokens(title: str) -> frozenset[str]:
    return frozenset(
        w for w in _WORD.findall(unicodedata.normalize("NFKC", title).casefold()) if w not in _STOP
    )


def _surname(author: str) -> str:
    name = unicodedata.normalize("NFKC", author).casefold().strip()
    if "," in name:
        name = name.split(",", 1)[0]
    else:
        parts = name.split()
        name = parts[-1] if parts else ""
    return "".join(_WORD.findall(name))


@dataclass(frozen=True)
class PaperFacts:
    id: uuid.UUID
    title: str
    title_normalised: str
    authors: list[str]
    year: int | None
    doi: str | None


@dataclass(frozen=True)
class DuplicateCandidate:
    paper_a: uuid.UUID
    paper_b: uuid.UUID
    reason: str  # same_title | similar_title
    score: float
    shared_authors: list[str]
    same_year: bool


def candidates(
    papers: list[PaperFacts], dismissed: set[tuple[uuid.UUID, uuid.UUID]]
) -> list[DuplicateCandidate]:
    """Pairs worth a human look. Exact normalised-title matches always qualify; otherwise titles
    must be very similar AND agree on year (when both are known) AND share an author surname (when
    both have authors). A DOI match cannot occur here: the database refuses duplicate DOIs."""
    out: list[DuplicateCandidate] = []
    tokens = {p.id: _tokens(p.title) for p in papers}
    ordered = sorted(papers, key=lambda p: str(p.id))
    for i, a in enumerate(ordered):
        for b in ordered[i + 1 :]:
            if (a.id, b.id) in dismissed:
                continue
            same_year = a.year is not None and a.year == b.year
            if a.year is not None and b.year is not None and a.year != b.year:
                if a.title_normalised != b.title_normalised:
                    continue
            surnames_a = {s for s in map(_surname, a.authors) if s}
            surnames_b = {s for s in map(_surname, b.authors) if s}
            shared = sorted(surnames_a & surnames_b)
            if a.title_normalised and a.title_normalised == b.title_normalised:
                out.append(DuplicateCandidate(a.id, b.id, "same_title", 1.0, shared, same_year))
                continue
            ta, tb = tokens[a.id], tokens[b.id]
            if not ta or not tb:
                continue
            score = len(ta & tb) / len(ta | tb)
            if score < SIMILARITY_MIN:
                continue
            if surnames_a and surnames_b and not shared:
                continue
            out.append(
                DuplicateCandidate(a.id, b.id, "similar_title", round(score, 3), shared, same_year)
            )
    out.sort(key=lambda c: (-c.score, str(c.paper_a), str(c.paper_b)))
    return out
