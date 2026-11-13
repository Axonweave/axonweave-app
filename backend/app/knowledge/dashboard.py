"""Learner Intelligence dashboard figures (Milestone 6.9). Pure aggregation over concept facts:
every number is a count of stored states, nothing is estimated. A concept with no evidence is
"unassessed" and is never counted as weak; weakness is only ever a demonstrated state."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime
from typing import Any

from app.repositories.learner_dashboard_repository import DashConcept, DashMisconception

STATES = (
    "NOT_ASSESSED",
    "INSUFFICIENT_EVIDENCE",
    "LEARNING",
    "DEVELOPING",
    "PROFICIENT",
    "STRONG",
)
SUFFICIENT = ("LEARNING", "DEVELOPING", "PROFICIENT", "STRONG")
NEEDS_WORK = ("LEARNING", "DEVELOPING")
NO_EVIDENCE = ("NOT_ASSESSED", "INSUFFICIENT_EVIDENCE")
LIST_CAP = 20


def _item(c: DashConcept, **extra: Any) -> dict[str, Any]:
    return {
        "node_id": c.id,
        "name": c.name,
        "subject_id": c.subject_id,
        "subject_name": c.subject_name,
        "state": c.state,
        "mastery": c.mastery,
        **extra,
    }


def _distribution(cs: list[DashConcept]) -> dict[str, int]:
    out = {s: 0 for s in STATES}
    for c in cs:
        out[c.state] = out.get(c.state, 0) + 1
    return out


def overview(cs: list[DashConcept], misconceptions: int, recommendations: int) -> dict[str, Any]:
    d = _distribution(cs)
    return {
        "tracked": len(cs),
        "assessed": sum(1 for c in cs if c.state != "NOT_ASSESSED"),
        "sufficient_evidence": sum(1 for c in cs if c.state in SUFFICIENT),
        "strong": d["STRONG"],
        "proficient": d["PROFICIENT"],
        "developing": d["DEVELOPING"],
        "weak": d["LEARNING"],
        "insufficient_evidence": d["INSUFFICIENT_EVIDENCE"],
        "unassessed": d["NOT_ASSESSED"],
        "misconceptions": misconceptions,
        "recommendations": recommendations,
    }


def subjects(
    cs: list[DashConcept], missing_prereqs: dict[uuid.UUID | None, int]
) -> list[dict[str, Any]]:
    groups: dict[uuid.UUID | None, list[DashConcept]] = defaultdict(list)
    for c in cs:
        groups[c.subject_id].append(c)
    out = []
    for sid, group in groups.items():
        d = _distribution(group)
        out.append(
            {
                "subject_id": sid,
                "subject_name": group[0].subject_name,
                "total": len(group),
                "assessed": sum(1 for c in group if c.state != "NOT_ASSESSED"),
                "distribution": d,
                "weak": [c.name for c in group if c.state == "LEARNING"][:5],
                "strong": [c.name for c in group if c.state == "STRONG"][:5],
                "unassessed": d["NOT_ASSESSED"],
                "missing_prerequisites": missing_prereqs.get(sid, 0),
            }
        )
    out.sort(key=lambda s: (s["subject_name"] is None, s["subject_name"] or ""))
    return out


def gaps(
    cs: list[DashConcept],
    edges: list[tuple[uuid.UUID, uuid.UUID, str]],
    misconceptions: list[DashMisconception],
    now: datetime,
) -> dict[str, list[dict[str, Any]]]:
    by_id = {c.id: c for c in cs}
    weak = sorted(
        (c for c in cs if c.state == "LEARNING"), key=lambda c: (c.mastery or 0.0, c.name)
    )

    needed_for: dict[uuid.UUID, list[str]] = defaultdict(list)
    for s, t, ty in edges:
        if ty == "PREREQUISITE_OF":
            p, x = by_id.get(s), by_id.get(t)
        else:
            p, x = by_id.get(t), by_id.get(s)
        if p is None or x is None or p.id == x.id or x.state not in NEEDS_WORK:
            continue
        # demonstrated: the prerequisite itself is weak or developing; no_evidence: never assessed
        if p.state in NEEDS_WORK or p.state in NO_EVIDENCE:
            needed_for[p.id].append(x.name)
    prereqs = [
        _item(
            by_id[pid],
            kind="demonstrated" if by_id[pid].state in NEEDS_WORK else "no_evidence",
            needed_for=sorted(set(names))[:5],
        )
        for pid, names in needed_for.items()
    ]
    prereqs.sort(key=lambda i: (i["kind"] != "demonstrated", -len(i["needed_for"]), i["name"]))

    miscs = [
        {
            "id": m.id,
            "node_id": m.node_id,
            "name": by_id[m.node_id].name,
            "description": m.description,
            "confidence": m.confidence,
            "tentative": m.confidence < 0.7,
            "evidence_count": m.evidence_count,
            "status": m.status,
        }
        for m in misconceptions
        if m.node_id in by_id
    ]
    unassessed = sorted(
        (c for c in cs if c.state in NO_EVIDENCE and c.degree >= 2),
        key=lambda c: (-c.degree, c.name),
    )
    due = sorted(
        (c for c in cs if c.next_review_at is not None and c.next_review_at <= now),
        key=lambda c: (c.next_review_at or now, c.name),
    )
    return {
        "weak": [_item(c, evidence_count=c.evidence_count) for c in weak][:LIST_CAP],
        "missing_prerequisites": prereqs,  # uncapped: the caller counts per subject, then caps
        "misconceptions": miscs[:LIST_CAP],
        "unassessed_important": [_item(c, connections=c.degree) for c in unassessed][:LIST_CAP],
        "needs_revision": [_item(c, next_review_at=c.next_review_at) for c in due][:LIST_CAP],
    }
