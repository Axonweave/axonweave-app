"""Contradiction candidates between papers (Phase 7 M7.7, spec 29). Pure functions, no model call.

Two result claims from different papers are a candidate when they share at least two topic terms
and carry opposite polarity (one reports an improvement or positive effect, the other a decrease,
no effect or a failure). Before the pair is classified the papers' conditions (dataset, metrics,
experimental setup) are compared, because a difference in results does not by itself mean that the
papers contradict each other (spec 29)."""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass

from app.research.claims import LoadedPaper, StoredClaim
from app.research.comparison import terms_of

ANALYSIS_VERSION = "c1"
CLAIM_SECTIONS = ("results", "contributions")
MIN_SHARED_TERMS = 2
MAX_CLAIMS_PER_PAPER = 30
MAX_CANDIDATES = 50

_NEG = (
    "no significant",
    "no improvement",
    "no effect",
    "did not improve",
    "not effective",
    "ineffective",
    "decreas",
    "worse",
    "lower",
    "degrad",
    "inferior",
    "fails",
    "failed",
    "negative",
)
_POS = (
    "improv",
    "increas",
    "higher",
    "outperform",
    "better",
    "superior",
    "effective",
    "enhanc",
    "benefit",
    "positive",
    "gain",
)
_CUE_STEMS = tuple(c.split()[-1] for c in (*_NEG, *_POS))
_WORDS = re.compile(r"[a-z0-9\-]+")


def polarity(text: str) -> str | None:
    """'pos', 'neg' or None when the claim has no clear direction (or mixed cues)."""
    low = text.casefold()
    neg = sum(low.count(c) for c in _NEG)
    for c in _NEG:
        low = low.replace(c, " ")
    pos = sum(low.count(c) for c in _POS)
    if neg and not pos:
        return "neg"
    if pos and not neg:
        return "pos"
    return None


def topic_terms(text: str) -> set[str]:
    return {t for t in terms_of(text) if not t.startswith(_CUE_STEMS)}


@dataclass
class ContradictionCandidate:
    claim_a: StoredClaim
    claim_b: StoredClaim
    shared_terms: list[str]
    conditions: dict[str, object]
    category: str
    explanation: str
    confidence_label: str
    fingerprint: str


def _terms(paper: LoadedPaper, *sections: str, label_words: tuple[str, ...] = ()) -> set[str]:
    out: set[str] = set()
    for c in paper.in_section(*sections):
        if label_words and not (c.label and any(w in c.label.casefold() for w in label_words)):
            continue
        out |= terms_of(c.text)
    return out


def _compare(a: set[str], b: set[str]) -> str:
    if not a or not b:
        return "unknown"
    shared = a & b
    if not shared:
        return "different"
    return "same" if len(shared) / len(a | b) >= 0.5 else "partly_overlapping"


def conditions_of(a: LoadedPaper, b: LoadedPaper) -> dict[str, object]:
    rows: dict[str, object] = {}
    for key, sections, labels in (
        ("dataset", ("dataset",), ()),
        ("metrics", ("evaluation",), ()),
        ("setup", ("methodology",), ()),
    ):
        ta, tb = _terms(a, *sections, label_words=labels), _terms(b, *sections, label_words=labels)
        rows[key] = {
            "comparison": _compare(ta, tb),
            "shared": sorted(ta & tb)[:12],
            "only_a": sorted(ta - tb)[:12],
            "only_b": sorted(tb - ta)[:12],
        }
    rows["years"] = {"a": a.year, "b": b.year}
    return rows


def classify(conditions: dict[str, object]) -> tuple[str, str, str]:
    """(category, explanation, confidence) from the compared conditions."""

    def cmp(key: str) -> str:
        entry = conditions[key]
        assert isinstance(entry, dict)
        return str(entry["comparison"])

    dataset, metrics, setup = cmp("dataset"), cmp("metrics"), cmp("setup")
    if dataset == "unknown" and metrics == "unknown":
        return (
            "insufficient_evidence",
            "The analyses of these papers do not describe a dataset or evaluation metrics, so it "
            "cannot be judged whether the claims really conflict.",
            "low",
        )
    if metrics == "different":
        return (
            "metric_incompatible",
            "The papers report different evaluation metrics, so the claims may not be directly "
            "comparable.",
            "low",
        )
    if dataset == "different" or setup == "different":
        what = "datasets" if dataset == "different" else "experimental setups"
        return (
            "context_dependent",
            f"The papers use different {what}; the findings may differ because of the conditions "
            "rather than contradict each other.",
            "low",
        )
    if dataset in ("same", "partly_overlapping") and metrics in ("same", "partly_overlapping"):
        return (
            "genuine",
            "The papers report opposite outcomes on the same topic with overlapping dataset and "
            "metric descriptions. Review both claims and their evidence before concluding.",
            "moderate",
        )
    return (
        "insufficient_evidence",
        "Some conditions (dataset or metrics) are missing from the analyses, so the comparison is "
        "incomplete.",
        "low",
    )


def fingerprint(a: StoredClaim, b: StoredClaim) -> str:
    ids = sorted((f"{a.paper_id}:{a.section}:{a.index}", f"{b.paper_id}:{b.section}:{b.index}"))
    return hashlib.sha256("|".join(ids).encode()).hexdigest()


def generate_candidates(papers: list[LoadedPaper]) -> list[ContradictionCandidate]:
    pool: dict[uuid.UUID, list[tuple[StoredClaim, str, set[str]]]] = {}
    for p in papers:
        items = []
        for c in p.in_section(*CLAIM_SECTIONS)[:MAX_CLAIMS_PER_PAPER]:
            pol = polarity(c.text)
            if pol:
                items.append((c, pol, topic_terms(c.text)))
        pool[p.paper_id] = items
    found: list[ContradictionCandidate] = []
    for i, pa in enumerate(papers):
        for pb in papers[i + 1 :]:
            cond = conditions_of(pa, pb)
            category, explanation, confidence = classify(cond)
            for ca, pola, ta in pool[pa.paper_id]:
                for cb, polb, tb in pool[pb.paper_id]:
                    shared = ta & tb
                    if pola == polb or len(shared) < MIN_SHARED_TERMS:
                        continue
                    found.append(
                        ContradictionCandidate(
                            ca,
                            cb,
                            sorted(shared)[:12],
                            cond,
                            category,
                            explanation,
                            confidence,
                            fingerprint(ca, cb),
                        )
                    )
    found.sort(key=lambda c: (c.category != "genuine", -len(c.shared_terms), c.fingerprint))
    return found[:MAX_CANDIDATES]
