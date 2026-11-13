"""Parsing and verification of extraction output (D-126, spec 9.5).

The model is untrusted. After the schema check, every item is verified against the passages that
were actually sent: a concept or relationship survives only if at least one of its quotations is
found (whitespace, case and quote-style insensitive) in the cited passage. Items that cannot be
verified are DROPPED, never stored. Nothing here logs text.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from app.ai.rag import escape_markup
from app.knowledge.normalise import normalise_name, normalise_passage
from app.knowledge.schemas import (
    EvidenceItem,
    ExtractedConcept,
    ExtractedRelationship,
    ExtractionOutput,
)
from app.models.knowledge import QUOTE_MAX_CHARS
from app.study.generators.base import OutputInvalid
from app.study.source_reader import SourceUnit
from app.study.validation import describe_errors, parse_json_object

_WORD = re.compile(r"[^\W\d_]{5,}", re.UNICODE)
DEFINITION_MIN_OVERLAP = 0.4
MAX_ALIASES = 8


@dataclass(frozen=True)
class VerifiedEvidence:
    unit: SourceUnit
    quote: str
    quote_hash: str  # SHA-256 of the normalised quotation (D-123)


@dataclass
class VerifiedConcept:
    name: str
    normalised_name: str
    node_type: str
    description: str | None
    definition: str | None
    aliases: list[str]
    difficulty: str | None
    confidence: float
    evidence: list[VerifiedEvidence] = field(default_factory=list)


@dataclass
class VerifiedRelationship:
    source: str  # normalised name of a concept in the same result
    target: str
    relationship_type: str
    statement_kind: str
    description: str | None
    confidence: float
    evidence: list[VerifiedEvidence] = field(default_factory=list)


@dataclass
class VerifiedOutput:
    concepts: list[VerifiedConcept]
    relationships: list[VerifiedRelationship]
    dropped: dict[str, int]


def parse_extraction(raw: str) -> ExtractionOutput:
    data = parse_json_object(raw)
    try:
        return ExtractionOutput.model_validate(data)
    except ValidationError as exc:
        raise OutputInvalid(describe_errors(exc)) from None


def _hash(normalised_quote: str) -> str:
    return hashlib.sha256(normalised_quote.encode("utf-8")).hexdigest()


class _Passages:
    """Normalised text of each numbered unit, plus the escaped form the model actually saw."""

    def __init__(self, units: Sequence[SourceUnit]) -> None:
        self.units = units
        self._plain = [normalise_passage(u.content) for u in units]
        self._seen = [normalise_passage(escape_markup(u.content)) for u in units]

    def verify(self, items: Sequence[EvidenceItem]) -> list[VerifiedEvidence]:
        out: list[VerifiedEvidence] = []
        seen: set[tuple[int, str]] = set()
        for item in items:
            idx = item.source - 1
            if idx < 0 or idx >= len(self.units):
                continue  # a number that was never sent: never trusted
            quote = normalise_passage(item.quote)
            if len(quote) < 3 or (idx, quote) in seen:
                continue
            if quote in self._plain[idx] or quote in self._seen[idx]:
                seen.add((idx, quote))
                shown = " ".join(item.quote.split())[:QUOTE_MAX_CHARS]
                out.append(VerifiedEvidence(self.units[idx], shown, _hash(quote)))
        return out

    def text_of(self, evidence: Sequence[VerifiedEvidence]) -> str:
        parts = []
        for ev in evidence:
            for i, unit in enumerate(self.units):
                if unit is ev.unit:
                    parts.append(self._plain[i])
        return " ".join(parts)


def _definition_grounded(definition: str, source_text: str) -> bool:
    """Cheap, deterministic check that a stated definition is made of words from the cited
    passages (spec 9.5: do not invent definitions absent from the source)."""
    words = {w.casefold() for w in _WORD.findall(definition)}
    if not words:
        return True
    hit = sum(1 for w in words if w in source_text)
    return hit / len(words) >= DEFINITION_MIN_OVERLAP


def verify(
    output: ExtractionOutput,
    units: Sequence[SourceUnit],
    *,
    max_concepts: int,
    max_relationships: int,
) -> VerifiedOutput:
    passages = _Passages(units)
    dropped = {"concepts": 0, "relationships": 0, "definitions": 0}

    by_name: dict[str, VerifiedConcept] = {}
    for concept in output.concepts:
        verified = _verify_concept(concept, passages, dropped)
        if verified is None:
            continue
        existing = by_name.get(verified.normalised_name)
        if existing is None:
            by_name[verified.normalised_name] = verified
            continue
        # The model repeated a concept: merge its evidence, keep the stronger fields.
        known = {e.quote_hash for e in existing.evidence}
        existing.evidence.extend(e for e in verified.evidence if e.quote_hash not in known)
        existing.confidence = max(existing.confidence, verified.confidence)
        existing.description = existing.description or verified.description
        existing.definition = existing.definition or verified.definition
        for alias in verified.aliases:
            if alias not in existing.aliases and len(existing.aliases) < MAX_ALIASES:
                existing.aliases.append(alias)

    concepts = sorted(by_name.values(), key=lambda c: (-c.confidence, c.normalised_name))
    if len(concepts) > max_concepts:
        dropped["concepts"] += len(concepts) - max_concepts
        concepts = concepts[:max_concepts]

    lookup: dict[str, str] = {c.normalised_name: c.normalised_name for c in concepts}
    for c in concepts:  # an alias never overrides another concept's own name
        for alias in c.aliases:
            lookup.setdefault(normalise_name(alias), c.normalised_name)

    relationships: dict[tuple[str, str, str], VerifiedRelationship] = {}
    for rel in output.relationships:
        verified_rel = _verify_relationship(rel, passages, lookup)
        if verified_rel is None:
            dropped["relationships"] += 1
            continue
        key = (verified_rel.source, verified_rel.target, verified_rel.relationship_type)
        relationships.setdefault(key, verified_rel)
    ranked = sorted(relationships.values(), key=lambda r: -r.confidence)
    if len(ranked) > max_relationships:
        dropped["relationships"] += len(ranked) - max_relationships
        ranked = ranked[:max_relationships]
    return VerifiedOutput(concepts, ranked, dropped)


def _verify_concept(
    concept: ExtractedConcept, passages: _Passages, dropped: dict[str, int]
) -> VerifiedConcept | None:
    norm = normalise_name(concept.name)
    evidence = passages.verify(concept.evidence)
    if not norm or not evidence:
        dropped["concepts"] += 1
        return None
    definition = concept.definition.strip() if concept.definition else None
    if definition and not _definition_grounded(definition, passages.text_of(evidence)):
        definition = None  # kept as a concept, but an unsupported definition is not stored
        dropped["definitions"] += 1
    aliases: list[str] = []
    for alias in concept.aliases:
        shown = " ".join(alias.split())[:200]
        key = normalise_name(shown)
        if key and key != norm and shown not in aliases and len(aliases) < MAX_ALIASES:
            aliases.append(shown)
    return VerifiedConcept(
        name=" ".join(concept.name.split()),
        normalised_name=norm,
        node_type=concept.type,
        description=concept.description.strip() if concept.description else None,
        definition=definition,
        aliases=aliases,
        difficulty=concept.difficulty,
        confidence=concept.confidence,
        evidence=evidence,
    )


def _verify_relationship(
    rel: ExtractedRelationship, passages: _Passages, lookup: dict[str, str]
) -> VerifiedRelationship | None:
    source = lookup.get(normalise_name(rel.source))
    target = lookup.get(normalise_name(rel.target))
    if source is None or target is None or source == target:
        return None
    evidence = passages.verify(rel.evidence)
    if not evidence:
        return None
    return VerifiedRelationship(
        source=source,
        target=target,
        relationship_type=rel.type,
        statement_kind=rel.statement,
        description=rel.description.strip() if rel.description else None,
        confidence=rel.confidence,
        evidence=evidence,
    )


def stats_of(result: VerifiedOutput) -> dict[str, Any]:
    return {
        "concepts": len(result.concepts),
        "relationships": len(result.relationships),
        "dropped": dict(result.dropped),
    }
