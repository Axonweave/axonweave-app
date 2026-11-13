"""Research gap candidates (Phase 7 M7.6, spec 28). Pure functions, no model call.

A candidate is built only from what the analysed papers themselves state: limitations and future
work claims (each with its verified quotation) that match a gap category. Counter-evidence is
searched in the same collection: claims in which a paper says it addresses the same thing. The
output describes the analysed collection only; it never claims that no other research exists, and
confidence is a plain label (strong, moderate, preliminary, insufficient), never a probability.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field

from app.research.claims import LoadedPaper, StoredClaim

ANALYSIS_VERSION = "g1"
COLLECTION_NOTE = (
    "This finding is limited to the papers currently included and analysed in this research "
    "project. It does not show that no other research exists on the topic."
)

# category -> (label, wording of the suggested direction, keywords found in a stated limitation)
CATEGORIES: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "dataset": (
        "Dataset limitations",
        "Consider evaluating on additional, larger or more varied datasets, with external "
        "validation.",
        (
            "dataset",
            "data set",
            "sample size",
            "small sample",
            "limited data",
            "synthetic data",
            "external validation",
            "data availability",
            "annotated data",
            "training data",
        ),
    ),
    "population": (
        "Population or sample coverage",
        "Consider studies with other populations, wider sampling or other regions.",
        (
            "population",
            "participants",
            "demographic",
            "geograph",
            "single site",
            "single-center",
            "single centre",
            "one country",
            "cohort",
            "sample of",
        ),
    ),
    "evaluation": (
        "Evaluation limitations",
        "Consider additional metrics, baselines, comparisons or robustness tests.",
        (
            "metric",
            "benchmark",
            "baseline",
            "robustness",
            "ablation",
            "comparison with",
            "evaluation",
            "statistical test",
            "significance",
        ),
    ),
    "reproducibility": (
        "Reproducibility",
        "Consider replications with shared code, data and full experimental details.",
        (
            "reproduc",
            "replicat",
            "open-source",
            "code is not",
            "hyperparameter",
            "implementation detail",
            "not publicly",
        ),
    ),
    "generalisation": (
        "Generalisation",
        "Consider testing across other datasets, environments or conditions.",
        (
            "generali",
            "unseen",
            "out-of-distribution",
            "other datasets",
            "transfer",
            "different environment",
            "external datasets",
        ),
    ),
    "domain": (
        "Other domains",
        "Consider evaluating the approach in related domains, languages or tasks.",
        (
            "other domain",
            "different domain",
            "cross-domain",
            "other languages",
            "other tasks",
            "related domain",
            "other fields",
        ),
    ),
    "application": (
        "Practical application",
        "Consider studies of real-world use, deployment or practical constraints.",
        (
            "real-world",
            "real world",
            "deployment",
            "clinical",
            "practical",
            "industry",
            "in practice",
            "applied setting",
        ),
    ),
    "methodological": (
        "Methodological limitations",
        "Consider alternative methods, relaxed assumptions or approaches with lower cost.",
        (
            "assumption",
            "scalab",
            "computational cost",
            "complexity",
            "bias",
            "approximation",
            "simplif",
            "model is limited",
        ),
    ),
}

# Wording by which a paper says it addresses something: used to look for counter-evidence.
ADDRESSING_CUES = (
    "we address",
    "we release",
    "publicly available",
    "open-source",
    "open source",
    "we evaluate on",
    "we also evaluate",
    "we test on",
    "we show that",
    "we propose",
    "we validate",
    "externally validated",
    "multiple datasets",
    "several datasets",
)

STATED_SECTIONS = ("limitations", "future_work")
COUNTER_SECTIONS = ("contributions", "methodology", "evaluation", "dataset", "results")


@dataclass
class GapCandidate:
    category: str
    title: str
    description: str
    rationale: str
    confidence_label: str
    limitations: str
    suggested_direction: str
    supporting: list[StoredClaim]
    counter: list[StoredClaim]
    fingerprint: str
    paper_ids: list[uuid.UUID] = field(default_factory=list)


def _matches(claim: StoredClaim, keywords: tuple[str, ...]) -> bool:
    text = claim.text.casefold()
    return any(k in text for k in keywords)


def _label(n_papers: int, total: int, only_inferred: bool) -> str:
    if only_inferred:
        return "insufficient_evidence"
    if n_papers >= 3 and total >= 3:
        return "strong_candidate"
    if n_papers >= 2:
        return "moderate_candidate"
    return "preliminary_candidate"


def fingerprint(category: str, claims: list[StoredClaim]) -> str:
    ids = sorted(f"{c.paper_id}:{c.section}:{c.index}" for c in claims)
    return hashlib.sha256((category + "|" + ",".join(ids)).encode()).hexdigest()


def generate_candidates(papers: list[LoadedPaper]) -> list[GapCandidate]:
    total = len(papers)
    titles = {p.paper_id: p.title for p in papers}
    out: list[GapCandidate] = []
    for category, (name, direction, keywords) in CATEGORIES.items():
        supporting = [
            c for p in papers for c in p.in_section(*STATED_SECTIONS) if _matches(c, keywords)
        ]
        if not supporting:
            continue
        supporting_papers = sorted({c.paper_id for c in supporting}, key=str)
        # Counter-evidence: another statement in the collection about the same subject in which the
        # paper says it addresses it. It is shown next to the candidate, never hidden.
        counter = [
            c
            for p in papers
            for c in p.in_section(*COUNTER_SECTIONS)
            if _matches(c, keywords) and any(cue in c.text.casefold() for cue in ADDRESSING_CUES)
        ]
        only_inferred = all(c.origin == "ai_inferred" for c in supporting)
        label = _label(len(supporting_papers), total, only_inferred)
        names = ", ".join(titles[i] for i in supporting_papers[:5])
        more = f" and {len(supporting_papers) - 5} more" if len(supporting_papers) > 5 else ""
        description = (
            f"Within the {total} analysed paper{'s' if total != 1 else ''} currently included in "
            f"this research project, {len(supporting_papers)} "
            f"{'state' if len(supporting_papers) != 1 else 'states'} a limitation or future work "
            f"item related to: {name.lower()}."
        )
        rationale = f"Stated by: {names}{more}. " + (
            f"{len(counter)} statement{'s' if len(counter) != 1 else ''} in the collection "
            "describe work that addresses the same subject; read them before treating this as "
            "open."
            if counter
            else "No statement in the collection was found that addresses it."
        )
        out.append(
            GapCandidate(
                category=category,
                title=f"{name} reported across the collection",
                description=description,
                rationale=rationale,
                confidence_label=label,
                limitations=COLLECTION_NOTE
                + (
                    " The supporting statements are AI-inferred, not stated by the authors."
                    if only_inferred
                    else ""
                ),
                suggested_direction=direction,
                supporting=supporting,
                counter=counter,
                fingerprint=fingerprint(category, supporting),
                paper_ids=supporting_papers,
            )
        )
    order = {"strong_candidate": 0, "moderate_candidate": 1, "preliminary_candidate": 2}
    out.sort(key=lambda g: (order.get(g.confidence_label, 3), -len(g.supporting)))
    return out
