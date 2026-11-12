"""Pure scoring and aggregation for quiz attempts (Phase 5 M1, D-103, D-104, D-112).

Given the question rows and the stored per-question answer rows of a submitted attempt, compute the
counts, score and percentage. Used at submit and again after AI evaluation completes or is
retried. No I/O. In self-assessment mode (AI grading off) the result is identical to Phase 4.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.models.quiz import QuizAttemptAnswer, QuizQuestion
from app.study.quiz_grading import OBJECTIVE_TYPES

# An AI-graded answer at or above this fraction counts as "correct" in the counts (D-112). The
# awarded score itself stays fractional; this only decides which bucket the count goes in.
AI_CORRECT_THRESHOLD = 0.7
# A topic whose accuracy in an attempt is below this is suggested for revision (rule-based).
WEAK_TOPIC_BELOW = 60.0


def _answered(row: QuizAttemptAnswer) -> bool:
    return bool(row.submitted_answer)


@dataclass
class TopicStat:
    topic: str | None
    total: int = 0
    correct: int = 0
    awarded: float = 0.0
    available: float = 0.0

    @property
    def percentage(self) -> float | None:
        return round(self.awarded / self.available * 100, 1) if self.available else None


@dataclass
class Totals:
    total_questions: int = 0
    graded_questions: int = 0
    correct: int = 0
    incorrect: int = 0
    unanswered: int = 0
    not_graded: int = 0
    pending: int = 0
    failed: int = 0
    ai_assisted: int = 0
    score: float = 0.0
    max_score: float = 0.0
    topics: dict[str | None, TopicStat] = field(default_factory=dict)

    @property
    def percentage(self) -> float | None:
        return round(self.score / self.max_score * 100, 2) if self.max_score else None

    @property
    def evaluation_status(self) -> str:
        if self.failed:
            return "failed"
        if self.pending:
            return "pending"
        return "completed" if self.ai_assisted else "not_required"


def summarise(questions: list[QuizQuestion], rows: list[QuizAttemptAnswer]) -> Totals:
    by_question = {r.question_id: r for r in rows}
    t = Totals(total_questions=len(questions))
    for q in questions:
        row = by_question.get(q.id)
        if row is None:
            continue
        stat = t.topics.setdefault(q.topic, TopicStat(q.topic))
        stat.total += 1
        answered = _answered(row)
        if not answered:
            t.unanswered += 1
        if row.evaluation_status == "pending":
            t.pending += 1
        elif row.evaluation_status == "failed":
            t.failed += 1
        if row.ai_assisted:
            t.ai_assisted += 1
        if row.evaluation_status in ("pending", "failed"):
            continue  # waiting for evaluation: counted nowhere until graded, never as 0
        if row.evaluation_status == "not_graded":
            if answered:
                t.not_graded += 1
            continue
        # graded (objective, AI-graded, or an unanswered question that is simply 0)
        available = float(row.max_score)
        awarded = float(row.awarded_score)
        t.graded_questions += 1
        t.score += awarded
        t.max_score += available
        stat.available += available
        stat.awarded += awarded
        if answered:
            if row.is_correct:
                t.correct += 1
                stat.correct += 1
            else:
                t.incorrect += 1
    t.score = round(t.score, 2)
    t.max_score = round(t.max_score, 2)
    return t


def is_ai_graded_type(question_type: str) -> bool:
    return question_type not in OBJECTIVE_TYPES


def suggested_topics(t: Totals) -> list[str]:
    """Topics with at least one graded question and accuracy below the threshold, weakest first.
    Wording in the UI is "may need revision": this is a hint from one attempt, not a verdict."""
    weak = [
        s
        for s in t.topics.values()
        if s.topic and s.percentage is not None and s.percentage < WEAK_TOPIC_BELOW
    ]
    weak.sort(key=lambda s: (s.percentage if s.percentage is not None else 0.0, s.topic or ""))
    return [s.topic for s in weak if s.topic]


def topic_rows(t: Totals) -> list[dict[str, Any]]:
    out = [
        {
            "topic": s.topic,
            "questions": s.total,
            "correct": s.correct,
            "percentage": s.percentage,
        }
        for s in t.topics.values()
    ]
    out.sort(key=lambda r: (r["topic"] is None, str(r["topic"] or "").casefold()))
    return out


def money(value: float) -> Decimal:
    return Decimal(str(round(value, 2)))
