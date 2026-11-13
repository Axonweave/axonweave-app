"""Personalised recommendations from learner state and the knowledge graph (Milestone 6.8).

Pure and deterministic: facts in, ranked candidates out, no database and no model. Every score is
`base + adjustment`, both documented below and stored on the recommendation, so a ranking can be
explained and tested. A recommendation exists only when the facts that justify it are present:
nothing is suggested "just in case" and no reason text is invented.

Rules, base score and adjustment (higher scores rank first):

* review_misconception  90 (70 when the finding is tentative) + 10 x confidence
* study_prerequisite    80 + 10 x (1 - mastery of the prerequisite) + 5 if the dependent concept is
                        weak. A prerequisite that is itself weak or developing, of a concept the
                        learner is struggling with.
* revise_concept        70 + 20 x (1 - mastery). Concept state LEARNING (demonstrated weak).
* review_due            60 + min(20, 2 x days overdue). A flashcard covering the concept is due.
* revisit_chapter       55 + 5 x weak concepts (max 75). A chapter with 2+ weak concepts.
* practise_concept      50 + min(15, 5 x hard-question failures). 2+ wrong answers on hard items.
* study_related         40 + 10 x mastery of the related concept. A weak concept next to a related
                        concept the learner already handles well.
* assess_concept        30 + min(15, 3 x connections). A well-connected concept with no evidence.

Priority: score >= 75 high, >= 50 medium, otherwise low. At most one recommendation per concept (the
highest scoring one) and MAX_ITEMS overall. Spec items not available in this codebase and therefore
not used: user goals, exam deadlines, subject importance weights and question-type reattempts.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

HIGH_AT = 75.0
MEDIUM_AT = 50.0
MAX_ITEMS = 15
MAX_ASSESS = 5
MIN_DEGREE_TO_ASSESS = 2
WEAK = ("LEARNING",)
NEEDS_WORK = ("LEARNING", "DEVELOPING")
GOOD = ("PROFICIENT", "STRONG")
TENTATIVE_BELOW = 0.7


@dataclass(frozen=True)
class ConceptFacts:
    id: uuid.UUID
    name: str
    state: str  # NOT_ASSESSED when there is no evidence
    mastery: float | None
    confidence: float
    evidence_count: int
    next_review_at: datetime | None
    chapter_id: uuid.UUID | None
    chapter_title: str | None
    degree: int
    hard_failures: int


@dataclass(frozen=True)
class MisconceptionFacts:
    id: uuid.UUID
    node_id: uuid.UUID
    description: str
    confidence: float
    action: str | None
    evidence_count: int


@dataclass(frozen=True)
class Edge:
    source: uuid.UUID
    target: uuid.UUID
    type: str


@dataclass(frozen=True)
class Candidate:
    type: str
    node_id: uuid.UUID | None
    topic_name: str
    dedupe_key: str
    score: float
    priority: str
    reason: str
    action: str
    evidence: dict[str, Any] = field(default_factory=dict)


def priority_for(score: float) -> str:
    if score >= HIGH_AT:
        return "high"
    return "medium" if score >= MEDIUM_AT else "low"


def _pct(v: float | None) -> str:
    return f"{int((v or 0) * 100 + 0.5)}%"


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _make(
    kind: str,
    node: ConceptFacts | None,
    key: str,
    base: float,
    adjustment: float,
    reason: str,
    action: str,
    facts: dict[str, Any],
    topic: str | None = None,
) -> Candidate:
    score = round(base + adjustment, 2)
    return Candidate(
        type=kind,
        node_id=node.id if node else None,
        topic_name=(topic or (node.name if node else ""))[:120],
        dedupe_key=f"learner:{kind}:{key}"[:160],
        score=score,
        priority=priority_for(score),
        reason=reason,
        action=action[:300],
        evidence={
            "rule": kind,
            "base": base,
            "adjustment": round(adjustment, 2),
            "score": score,
            **facts,
        },
    )


def _state_facts(c: ConceptFacts) -> dict[str, Any]:
    return {
        "state": c.state,
        "mastery": c.mastery,
        "confidence": c.confidence,
        "evidence_count": c.evidence_count,
    }


def rank(
    concepts: list[ConceptFacts],
    misconceptions: list[MisconceptionFacts],
    edges: list[Edge],
    now: datetime,
) -> list[Candidate]:
    by_id = {c.id: c for c in concepts}
    out: list[Candidate] = []

    for m in misconceptions:
        node = by_id.get(m.node_id)
        if node is None:
            continue
        tentative = m.confidence < TENTATIVE_BELOW
        lead = (
            "Your answers suggest"
            if tentative
            else "You seem to have a recurring misunderstanding:"
        )
        out.append(
            _make(
                "review_misconception",
                node,
                str(m.id),
                70.0 if tentative else 90.0,
                10.0 * m.confidence,
                f"{lead} {m.description.rstrip('.')} (on {node.name}, from "
                f"{_plural(m.evidence_count, 'wrong answer')}).",
                m.action or f"Review {node.name} and the answers you got wrong.",
                {
                    "misconception_id": str(m.id),
                    "confidence": m.confidence,
                    "tentative": tentative,
                    "evidence_count": m.evidence_count,
                },
                topic=node.name,
            )
        )

    # prerequisites: P must be understood before X (P PREREQUISITE_OF X, or X DEPENDS_ON P)
    best_prereq: dict[uuid.UUID, tuple[ConceptFacts, list[ConceptFacts]]] = {}
    for e in edges:
        if e.type == "PREREQUISITE_OF":
            p, x = by_id.get(e.source), by_id.get(e.target)
        elif e.type == "DEPENDS_ON":
            x, p = by_id.get(e.source), by_id.get(e.target)
        else:
            continue
        if p is None or x is None or p.id == x.id:
            continue
        if x.state in NEEDS_WORK and p.state in NEEDS_WORK:
            dependants = best_prereq.setdefault(p.id, (p, []))[1]
            dependants.append(x)
    for p, dependants in best_prereq.values():
        dependants.sort(key=lambda d: (0 if d.state in WEAK else 1, d.name))
        x = dependants[0]
        names = ", ".join(d.name for d in dependants[:3])
        out.append(
            _make(
                "study_prerequisite",
                p,
                str(p.id),
                80.0,
                10.0 * (1 - (p.mastery or 0.0)) + (5.0 if x.state in WEAK else 0.0),
                f"Review {p.name} before moving on to {names}: it is a prerequisite, and your "
                f"results on {p.name} (estimate {_pct(p.mastery)}) show you need more practice.",
                f"Revise {p.name}, then return to {x.name}.",
                {**_state_facts(p), "needed_for": [d.name for d in dependants[:5]]},
            )
        )

    weak_by_chapter: dict[uuid.UUID, list[ConceptFacts]] = {}
    for c in concepts:
        if c.state in WEAK:
            out.append(
                _make(
                    "revise_concept",
                    c,
                    str(c.id),
                    70.0,
                    20.0 * (1 - (c.mastery or 0.0)),
                    f"Your understanding of {c.name} is still being learned: estimate "
                    f"{_pct(c.mastery)} from {_plural(c.evidence_count, 'result')}.",
                    f"Revise {c.name} and attempt another quiz on it.",
                    _state_facts(c),
                )
            )
            if c.chapter_id is not None:
                weak_by_chapter.setdefault(c.chapter_id, []).append(c)
        if c.next_review_at is not None and c.next_review_at <= now:
            days = max(0, (now - c.next_review_at).days)
            out.append(
                _make(
                    "review_due",
                    c,
                    str(c.id),
                    60.0,
                    min(20.0, 2.0 * days),
                    f"A flashcard covering {c.name} is due for review"
                    + (f" ({_plural(days, 'day')} overdue)." if days else " today."),
                    f"Review the {c.name} flashcards that are due.",
                    {**_state_facts(c), "overdue_days": days},
                )
            )
        if c.hard_failures >= 2 and c.state in ("LEARNING", "DEVELOPING", "PROFICIENT"):
            out.append(
                _make(
                    "practise_concept",
                    c,
                    str(c.id),
                    50.0,
                    min(15.0, 5.0 * c.hard_failures),
                    f"You answered {_plural(c.hard_failures, 'hard question')} on {c.name} "
                    "incorrectly.",
                    f"Practise the harder questions on {c.name}.",
                    {**_state_facts(c), "hard_failures": c.hard_failures},
                )
            )

    for chapter_id, weak in weak_by_chapter.items():
        if len(weak) >= 2:
            title = weak[0].chapter_title or "this chapter"
            out.append(
                _make(
                    "revisit_chapter",
                    None,
                    str(chapter_id),
                    55.0,
                    min(20.0, 5.0 * len(weak)),
                    f"{_plural(len(weak), 'concept')} in {title} are still being learned: "
                    + ", ".join(sorted(w.name for w in weak)[:4])
                    + ".",
                    f"Revisit {title}.",
                    {"chapter_id": str(chapter_id), "weak_concepts": sorted(w.name for w in weak)},
                    topic=title,
                )
            )

    # a weak concept beside a related concept the learner already handles well
    for e in edges:
        if e.type != "RELATED_TO":
            continue
        for a_id, b_id in ((e.source, e.target), (e.target, e.source)):
            a, b = by_id.get(a_id), by_id.get(b_id)
            if a is not None and b is not None and a.state in WEAK and b.state in GOOD:
                out.append(
                    _make(
                        "study_related",
                        a,
                        f"{a.id}:{b.id}",
                        40.0,
                        10.0 * (b.mastery or 0.0),
                        f"You are doing well on {b.name}, which is related to {a.name}. "
                        f"Comparing them can help with {a.name}.",
                        f"Compare {a.name} with {b.name}.",
                        {**_state_facts(a), "related": b.name, "related_mastery": b.mastery},
                    )
                )

    unassessed = sorted(
        (c for c in concepts if c.state == "NOT_ASSESSED" and c.degree >= MIN_DEGREE_TO_ASSESS),
        key=lambda c: (-c.degree, c.name),
    )[:MAX_ASSESS]
    for c in unassessed:
        out.append(
            _make(
                "assess_concept",
                c,
                str(c.id),
                30.0,
                min(15.0, 3.0 * c.degree),
                f"{c.name} is connected to {_plural(c.degree, 'other concept')} in your material "
                "but you have not been assessed on it yet.",
                f"Take a quiz or review flashcards that cover {c.name}.",
                {"state": "NOT_ASSESSED", "connections": c.degree},
            )
        )

    # one recommendation per concept (the highest scoring), chapters keyed by chapter
    out.sort(key=lambda r: (-r.score, r.topic_name, r.dedupe_key))
    chosen: list[Candidate] = []
    seen_nodes: set[uuid.UUID] = set()
    for r in out:
        if r.node_id is not None:
            if r.node_id in seen_nodes:
                continue
            seen_nodes.add(r.node_id)
        chosen.append(r)
    return chosen[:MAX_ITEMS]
