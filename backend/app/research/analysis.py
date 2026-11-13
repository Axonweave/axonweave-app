"""Parsing and verification of paper-analysis output (Phase 7 M7.3, spec 25).

The model is untrusted. After the schema check every claim is verified against the passages that
were actually sent: it survives only if at least one of its quotations is found (whitespace, case
and quote-style insensitive) in the cited passage. Claims that cannot be verified are DROPPED and
counted, never stored. A section the paper does not cover stays empty: the UI says "Not reported
in the available paper." and nothing is invented. Nothing here logs text.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.knowledge.normalise import normalise_passage
from app.knowledge.schemas import EvidenceItem
from app.knowledge.validation import VerifiedEvidence, _Passages
from app.models.research import SECTIONS
from app.study.generators.base import OutputInvalid
from app.study.source_reader import SourceUnit
from app.study.validation import describe_errors, parse_json_object

MAX_ITEMS_PER_SECTION = 25
NOT_REPORTED = "Not reported in the available paper."

TASK_BLOCK = """TASK
Extract what the paper reports in each section below. Reply with ONE JSON object of exactly this
shape and nothing else (use {"items": []} for a section the passages do not cover):
{
  "research_problem": {"items": [
    {"label": null, "text": "...", "origin": "reported", "confidence": 0.0,
     "evidence": [{"source": 1, "quote": "exact words copied from passage 1"}]}
  ]},
  "objectives": {"items": []}, "methodology": {"items": []}, "dataset": {"items": []},
  "evaluation": {"items": []}, "results": {"items": []}, "contributions": {"items": []},
  "limitations": {"items": []}, "future_work": {"items": []}, "references": {"items": []}
}
Sections: research_problem (the problem and motivation), objectives (aims, research questions,
hypotheses), methodology (approach, models, procedure), dataset (data used, size, source),
evaluation (metrics, baselines, setup), results (findings with their numbers), contributions
(what the authors say is new), limitations, future_work, references (works the paper cites that
appear in the passages). Every quote must be copied word for word from the passage you cite."""


class AnalysisClaim(BaseModel):
    model_config = ConfigDict(extra="ignore")

    label: str | None = Field(default=None, max_length=80)
    text: str = Field(min_length=3, max_length=1200)
    origin: Literal["reported", "ai_inferred"] = "reported"
    confidence: float = Field(default=0.5, ge=0, le=1)
    evidence: list[EvidenceItem] = Field(min_length=1, max_length=5)


class AnalysisSection(BaseModel):
    model_config = ConfigDict(extra="ignore")

    items: list[AnalysisClaim] = Field(default_factory=list, max_length=60)


class AnalysisOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    research_problem: AnalysisSection = Field(default_factory=AnalysisSection)
    objectives: AnalysisSection = Field(default_factory=AnalysisSection)
    methodology: AnalysisSection = Field(default_factory=AnalysisSection)
    dataset: AnalysisSection = Field(default_factory=AnalysisSection)
    evaluation: AnalysisSection = Field(default_factory=AnalysisSection)
    results: AnalysisSection = Field(default_factory=AnalysisSection)
    contributions: AnalysisSection = Field(default_factory=AnalysisSection)
    limitations: AnalysisSection = Field(default_factory=AnalysisSection)
    future_work: AnalysisSection = Field(default_factory=AnalysisSection)
    references: AnalysisSection = Field(default_factory=AnalysisSection)


@dataclass
class VerifiedClaim:
    label: str | None
    text: str
    origin: str
    confidence: float
    evidence: list[VerifiedEvidence] = field(default_factory=list)


@dataclass
class VerifiedAnalysis:
    sections: dict[str, list[VerifiedClaim]]
    dropped: int

    @property
    def claim_count(self) -> int:
        return sum(len(v) for v in self.sections.values())


def parse_analysis(raw: str) -> AnalysisOutput:
    data = parse_json_object(raw)
    try:
        return AnalysisOutput.model_validate(data)
    except ValidationError as exc:
        raise OutputInvalid(describe_errors(exc)) from None


def verify_analysis(output: AnalysisOutput, units: Sequence[SourceUnit]) -> VerifiedAnalysis:
    passages = _Passages(units)
    sections: dict[str, list[VerifiedClaim]] = {name: [] for name in SECTIONS}
    dropped = 0
    for name in SECTIONS:
        seen: set[str] = set()
        for claim in getattr(output, name).items:
            key = normalise_passage(claim.text)
            if (
                key in seen
                or len(sections[name]) >= MAX_ITEMS_PER_SECTION
                # Inference is allowed for limitations only (spec 25.2); elsewhere it is dropped.
                or (claim.origin == "ai_inferred" and name != "limitations")
            ):
                dropped += 1
                continue
            evidence = passages.verify(claim.evidence)
            if not evidence:
                dropped += 1
                continue
            seen.add(key)
            label = " ".join(claim.label.split()) if claim.label else None
            sections[name].append(
                VerifiedClaim(
                    label=label or None,
                    text=" ".join(claim.text.split()),
                    origin=claim.origin,
                    confidence=round(float(claim.confidence), 3),
                    evidence=evidence,
                )
            )
    return VerifiedAnalysis(sections, dropped)


def merge_analyses(parts: Sequence[VerifiedAnalysis]) -> VerifiedAnalysis:
    """Combine the results of several source batches of one paper, dropping repeats."""
    merged: dict[str, list[VerifiedClaim]] = {name: [] for name in SECTIONS}
    dropped = sum(p.dropped for p in parts)
    for name in SECTIONS:
        seen: set[str] = set()
        for part in parts:
            for claim in part.sections[name]:
                key = normalise_passage(claim.text)
                if key in seen or len(merged[name]) >= MAX_ITEMS_PER_SECTION:
                    dropped += 1
                    continue
                seen.add(key)
                merged[name].append(claim)
    return VerifiedAnalysis(merged, dropped)
