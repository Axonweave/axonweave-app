"""Rule-based learner mastery model, version `rb-1` (Milestone 6.6, spec section 14).

Pure and deterministic: the same evidence snapshot and `now` always give the same result.
No database, no randomness, no model call. Every constant is named here with its reason, so a result
can be explained and a change needs a new `CALCULATION_VERSION`.

How an estimate is built
------------------------
Each piece of evidence has a value v in [0, 1] and a weight w = reliability x difficulty x recency.

* reliability: a graded quiz answer is direct, objective evidence (1.0); one graded with AI help
  is a little less certain (0.85); a flashcard rating is the learner's own recall judgement (0.7).
* difficulty: passing an easy item says less than passing a hard one. Weights: easy 0.6, medium
  1.0, hard 1.3.
  Unknown difficulty counts as medium.
* recency: weight halves every 30 days but never falls below 0.25, so old results fade without being
  erased (14.3).

The estimate is a weighted mean pulled toward a neutral prior of 0.5 worth PRIOR_WEIGHT units of
evidence: mastery = (sum(w*v) + 0.5*PRIOR_WEIGHT) / (sum(w) + PRIOR_WEIGHT). The prior is why one
easy correct answer cannot make a concept strong and one recent failure cannot make it look lost.

Confidence is sum(w) / (sum(w) + CONFIDENCE_HALF): about three typical items give 0.5.

State (14.4)
------------
* NOT_ASSESSED: no evidence. There is no score, and it is never described as weak.
* INSUFFICIENT_EVIDENCE: fewer than MIN_EVENTS events or confidence below MIN_CONFIDENCE.
  The score is stored but not turned into a verdict.
* otherwise by mastery: < 0.40 LEARNING, < 0.65 DEVELOPING, < 0.85 PROFICIENT, else STRONG. STRONG
  also needs confidence >= STRONG_CONFIDENCE, otherwise it is reported as PROFICIENT.
Only LEARNING means "demonstrated weak understanding".
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

CALCULATION_VERSION = "rb-1"

RELIABILITY = {"quiz_answer": 1.0, "quiz_answer_ai": 0.85, "flashcard_review": 0.7}
DIFFICULTY_WEIGHT = {"easy": 0.6, "medium": 1.0, "hard": 1.3}
HALF_LIFE_DAYS = 30.0
RECENCY_FLOOR = 0.25
PRIOR_VALUE = 0.5
PRIOR_WEIGHT = 1.0
CONFIDENCE_HALF = 3.0
MIN_EVENTS = 3
MIN_CONFIDENCE = 0.4
STRONG_CONFIDENCE = 0.6
RECENT_DAYS = 14
LEARNING_BELOW = 0.40
DEVELOPING_BELOW = 0.65
PROFICIENT_BELOW = 0.85
REPEATED_ERROR_RUN = 2  # this many newest events in a row below 0.5
MAX_EXPLAINED_IDS = 20


@dataclass(frozen=True)
class EvidenceItem:
    id: str
    source_type: str
    value: float
    occurred_at: datetime
    difficulty: str | None = None
    ai_assisted: bool = False
    rating: str | None = None
    lapses: int | None = None


@dataclass(frozen=True)
class MasteryResult:
    state: str
    mastery: float | None
    confidence: float
    evidence_count: int
    last_evidence_at: datetime | None
    version: str
    explanation: dict[str, Any]


def _weight(item: EvidenceItem, now: datetime) -> float:
    key = (
        "quiz_answer_ai"
        if item.source_type == "quiz_answer" and item.ai_assisted
        else item.source_type
    )
    reliability = RELIABILITY.get(key, 0.7)
    difficulty = DIFFICULTY_WEIGHT.get(item.difficulty or "medium", 1.0)
    age_days = max((now - item.occurred_at).total_seconds() / 86400.0, 0.0)
    recency = max(RECENCY_FLOOR, 0.5 ** (age_days / HALF_LIFE_DAYS))
    return float(reliability * difficulty * recency)


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None


def _state(mastery: float, confidence: float, count: int) -> str:
    if count < MIN_EVENTS or confidence < MIN_CONFIDENCE:
        return "INSUFFICIENT_EVIDENCE"
    if mastery < LEARNING_BELOW:
        return "LEARNING"
    if mastery < DEVELOPING_BELOW:
        return "DEVELOPING"
    if mastery < PROFICIENT_BELOW or confidence < STRONG_CONFIDENCE:
        return "PROFICIENT"
    return "STRONG"


def calculate(items: list[EvidenceItem], now: datetime) -> MasteryResult:
    """Estimate mastery from a snapshot of evidence. Input order does not matter."""
    if not items:
        return MasteryResult(
            state="NOT_ASSESSED",
            mastery=None,
            confidence=0.0,
            evidence_count=0,
            last_evidence_at=None,
            version=CALCULATION_VERSION,
            explanation={"version": CALCULATION_VERSION, "facts": {"evidence_count": 0}},
        )
    ordered = sorted(items, key=lambda i: (i.occurred_at, i.id))
    weights = [_weight(i, now) for i in ordered]
    total_w = sum(weights)
    mastery = (
        sum(w * i.value for w, i in zip(weights, ordered, strict=True)) + PRIOR_VALUE * PRIOR_WEIGHT
    ) / (total_w + PRIOR_WEIGHT)
    mastery = round(mastery, 3)
    confidence = round(total_w / (total_w + CONFIDENCE_HALF), 3)
    count = len(ordered)
    state = _state(mastery, confidence, count)

    cutoff = now - timedelta(days=RECENT_DAYS)
    recent = [i.value for i in ordered if i.occurred_at >= cutoff]
    earlier = [i.value for i in ordered if i.occurred_at < cutoff]
    run = 0
    for item in reversed(ordered):
        if item.value < 0.5:
            run += 1
        else:
            break
    quiz = [i for i in ordered if i.source_type == "quiz_answer"]
    cards = [i for i in ordered if i.source_type == "flashcard_review"]
    facts: dict[str, Any] = {
        "evidence_count": count,
        "quiz_answers": len(quiz),
        "flashcard_reviews": len(cards),
        "quiz_average": _mean([i.value for i in quiz]),
        "flashcard_average": _mean([i.value for i in cards]),
        "recent_days": RECENT_DAYS,
        "recent_count": len(recent),
        "recent_average": _mean(recent),
        "earlier_count": len(earlier),
        "earlier_average": _mean(earlier),
        "repeated_errors": run if run >= REPEATED_ERROR_RUN else 0,
        "flashcard_lapses": max((i.lapses or 0 for i in cards), default=0),
        "weight_total": round(total_w, 3),
    }
    explanation = {
        "version": CALCULATION_VERSION,
        "facts": facts,
        "parameters": {
            "prior_value": PRIOR_VALUE,
            "prior_weight": PRIOR_WEIGHT,
            "half_life_days": HALF_LIFE_DAYS,
            "min_events": MIN_EVENTS,
        },
        "evidence_ids": [i.id for i in reversed(ordered)][:MAX_EXPLAINED_IDS],
    }
    return MasteryResult(
        state=state,
        mastery=mastery,
        confidence=confidence,
        evidence_count=count,
        last_evidence_at=ordered[-1].occurred_at,
        version=CALCULATION_VERSION,
        explanation=explanation,
    )


def _pct(value: float | None) -> str:
    return f"{math.floor((value or 0) * 100 + 0.5)}%"


def describe(name: str, result: MasteryResult) -> str:
    """Plain-language explanation built only from the stored facts (14.6): nothing is invented."""
    f = result.explanation.get("facts", {})
    n = int(f.get("evidence_count", 0))
    if result.state == "NOT_ASSESSED":
        return f"{name} has not been assessed yet. There is no quiz or flashcard evidence for it."
    parts = []
    if f.get("quiz_answers"):
        parts.append(f"{f['quiz_answers']} quiz answer{'s' if f['quiz_answers'] != 1 else ''}")
    if f.get("flashcard_reviews"):
        k = f["flashcard_reviews"]
        parts.append(f"{k} flashcard review{'s' if k != 1 else ''}")
    basis = " and ".join(parts)
    if result.state == "INSUFFICIENT_EVIDENCE":
        return (
            f"There is not enough evidence to judge {name} yet: {basis} "
            f"({n} event{'s' if n != 1 else ''}; at least {MIN_EVENTS} are needed)."
        )
    label = {
        "LEARNING": "still being learned",
        "DEVELOPING": "developing",
        "PROFICIENT": "proficient",
        "STRONG": "strong",
    }[result.state]
    estimate = _pct(result.mastery)
    text = f"Your understanding of {name} is {label}, based on {basis} (estimate {estimate})."
    ra, ea = f.get("recent_average"), f.get("earlier_average")
    if f.get("recent_count") and f.get("earlier_count") and ra is not None and ea is not None:
        if ra + 0.15 <= ea:
            text += (
                f" Recent results ({_pct(ra)} over the last {RECENT_DAYS} days) are weaker "
                f"than earlier ones ({_pct(ea)})."
            )
        elif ra >= ea + 0.15:
            text += (
                f" Recent results ({_pct(ra)} over the last {RECENT_DAYS} days) are stronger "
                f"than earlier ones ({_pct(ea)})."
            )
    if f.get("repeated_errors"):
        text += f" Your last {f['repeated_errors']} results on it were incorrect or weak."
    if f.get("flashcard_lapses"):
        text += f" A flashcard on it has lapsed {f['flashcard_lapses']} time(s)."
    return text
