"""Paper comparison engine (Phase 7 M7.4, spec 26). Pure functions, no model call, no I/O.

A comparison is assembled only from claims that were already extracted and verified (M7.3), so
every cell carries its quotations and nothing is invented. "Similarities" and "differences" are
plain term overlap between the selected papers' claims for one dimension: transparent and
repeatable, not a judgement. Whether results may be set against each other is decided by explicit
rules (same dataset, same metrics, no differing setup); anything the papers do not report stays
"Not reported." and counts as unconfirmed, never as comparable.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from itertools import combinations
from typing import Any

NOT_REPORTED = "Not reported."
MAX_ITEMS_PER_CELL = 8
MAX_TERMS = 12
SIMILARITY_THRESHOLD = 0.3  # minimum pairwise term overlap to call two papers' dimension "similar"
MIN_PAPERS = 2
MAX_PAPERS = 6


@dataclass(frozen=True)
class Dimension:
    key: str
    label: str
    section: str
    label_words: tuple[str, ...] = ()  # when set, only claims whose label contains one of these


DIMENSIONS: tuple[Dimension, ...] = (
    Dimension("research_problem", "Research problem", "research_problem"),
    Dimension("objectives", "Objectives and research questions", "objectives"),
    Dimension("methodology", "Methodology", "methodology"),
    Dimension(
        "models", "Models and algorithms", "methodology", ("model", "algorithm", "architecture")
    ),
    Dimension("dataset", "Dataset", "dataset"),
    Dimension("sample_size", "Sample size", "dataset", ("sample", "participants", "subjects")),
    Dimension("metrics", "Evaluation metrics", "evaluation", ("metric", "measure", "score")),
    Dimension("setup", "Experimental setup and evaluation", "evaluation"),
    Dimension("results", "Results", "results"),
    Dimension("contributions", "Contributions", "contributions"),
    Dimension("limitations", "Limitations", "limitations"),
    Dimension("future_work", "Future work", "future_work"),
)
DIMENSION_KEYS = tuple(d.key for d in DIMENSIONS)
_BY_KEY = {d.key: d for d in DIMENSIONS}

_STOP = frozenset(
    "this that with from have has had were was are been being their there these those which "
    "while where when what then than also into onto over under such other more most some "
    "each both between about after before during through using used use based paper study "
    "work results result approach method methods proposed show shows shown can may will would "
    "should could our its they them his her for and the not but".split()
)
_WORD = re.compile(r"[^\W_]+", re.UNICODE)


@dataclass
class ClaimInput:
    text: str
    label: str | None
    origin: str
    evidence: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class PaperInput:
    paper_id: str
    title: str
    extraction_id: str
    version_number: int
    claims: dict[str, list[ClaimInput]]  # by analysis section


def terms_of(text: str) -> set[str]:
    out: set[str] = set()
    for raw in _WORD.findall(text.casefold()):
        if raw in _STOP:
            continue
        if len(raw) >= 4 or (len(raw) >= 2 and any(c.isdigit() for c in raw)):
            out.add(raw)
    return out


def _claims_for(paper: PaperInput, dim: Dimension) -> list[ClaimInput]:
    claims = paper.claims.get(dim.section, [])
    if dim.label_words:
        claims = [
            c for c in claims if c.label and any(w in c.label.casefold() for w in dim.label_words)
        ]
    return claims[:MAX_ITEMS_PER_CELL]


def _jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if (a or b) else 0.0


def _agreement(term_sets: Sequence[set[str] | None]) -> str:
    """similar / different / unknown for one dimension across all papers."""
    if len(term_sets) < MIN_PAPERS or any(not t for t in term_sets):
        return "unknown"  # something is not reported: cannot be called similar
    sets = [t for t in term_sets if t]
    worst = min(_jaccard(a, b) for a, b in combinations(sets, 2))
    return "similar" if worst >= SIMILARITY_THRESHOLD else "different"


def _comparability(papers: Sequence[PaperInput]) -> dict[str, Any]:
    def agreement(key: str) -> str:
        dim = _BY_KEY[key]
        return _agreement([_union(_claims_for(p, dim)) or None for p in papers])

    dataset, metrics = agreement("dataset"), agreement("metrics")
    setup, methodology = agreement("setup"), agreement("methodology")
    directly = dataset == "similar" and metrics == "similar" and setup != "different"
    warnings: list[str] = []
    for name, value, noun in (
        ("dataset", dataset, "datasets"),
        ("metrics", metrics, "evaluation metrics"),
        ("setup", setup, "experimental setups"),
        ("methodology", methodology, "methodologies"),
    ):
        if value == "different":
            warnings.append(f"The papers use different {noun}.")
        elif value == "unknown" and name != "methodology":
            warnings.append(f"Whether the {noun} match could not be confirmed (not reported).")
    if not directly:
        warnings.append(
            "Numerical results are shown side by side but must not be treated as directly "
            "comparable."
        )
    return {
        "dataset": dataset,
        "metrics": metrics,
        "setup": setup,
        "methodology": methodology,
        "results_directly_comparable": directly,
        "warnings": warnings,
    }


def _union(claims: Sequence[ClaimInput]) -> set[str]:
    out: set[str] = set()
    for c in claims:
        out |= terms_of(c.text)
    return out


def build_comparison(
    papers: Sequence[PaperInput], dimensions: Sequence[str] | None = None
) -> dict[str, Any]:
    keys = [k for k in DIMENSION_KEYS if dimensions is None or k in dimensions]
    comparability = _comparability(papers)
    rows: list[dict[str, Any]] = []
    for key in keys:
        dim = _BY_KEY[key]
        cells: list[dict[str, Any]] = []
        term_sets: dict[str, set[str]] = {}
        for p in papers:
            claims = _claims_for(p, dim)
            term_sets[p.paper_id] = _union(claims)
            cells.append(
                {
                    "paper_id": p.paper_id,
                    "reported": bool(claims),
                    "items": [
                        {
                            "text": c.text,
                            "label": c.label,
                            "origin": c.origin,
                            "evidence": c.evidence,
                        }
                        for c in claims
                    ],
                }
            )
        reported = [c["paper_id"] for c in cells if c["reported"]]
        status = (
            "not_reported"
            if not reported
            else "complete"
            if len(reported) == len(papers)
            else "partial"
        )
        similarities: list[str] = []
        differences: list[dict[str, Any]] = []
        if len(reported) >= MIN_PAPERS:
            shared = set.intersection(*(term_sets[i] for i in reported))
            similarities = sorted(shared)[:MAX_TERMS]
            for pid in reported:
                others = set().union(*(term_sets[o] for o in reported if o != pid))
                differences.append(
                    {"paper_id": pid, "terms": sorted(term_sets[pid] - others)[:MAX_TERMS]}
                )
        rows.append(
            {
                "dimension": key,
                "label": dim.label,
                "status": status,
                "cells": cells,
                "similarities": similarities,
                "differences": differences,
                "not_reported_for": [p.paper_id for p in papers if p.paper_id not in reported],
                "directly_comparable": comparability["results_directly_comparable"]
                if key == "results"
                else None,
            }
        )
    return {
        "papers": [
            {
                "paper_id": p.paper_id,
                "title": p.title,
                "extraction_id": p.extraction_id,
                "version_number": p.version_number,
            }
            for p in papers
        ],
        "rows": rows,
        "comparability": comparability,
    }
