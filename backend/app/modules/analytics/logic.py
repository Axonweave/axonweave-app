"""Pure analytics logic (Phase 5 M5): topic labels with transparent thresholds and streaks.

No I/O. Labels are estimates from a few quiz answers, never a measure of mastery (spec 2.6): the
wording is "Strong", "Developing", "May need revision" and "Not enough data", and the thresholds
come from settings so they can be shown to the user.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

STRONG = "strong"
DEVELOPING = "developing"
NEEDS_REVISION = "needs_revision"
NOT_ENOUGH = "not_enough_data"


@dataclass(frozen=True)
class Thresholds:
    strong_at: float = 80.0
    needs_revision_below: float = 60.0
    min_answers: int = 3
    recent_attempts: int = 3
    trend_delta: float = 10.0


@dataclass
class TopicStat:
    topic: str
    attempts: int
    answers: int
    correct: int
    accuracy: float | None
    recent_accuracy: float | None
    previous_accuracy: float | None
    trend: str | None
    status: str
    last_attempt_at: datetime | None


def _pct(awarded: float, available: float) -> float | None:
    return round(awarded / available * 100, 1) if available > 0 else None


def label_for(accuracy: float | None, answers: int, t: Thresholds) -> str:
    if accuracy is None or answers < t.min_answers:
        return NOT_ENOUGH
    if accuracy >= t.strong_at:
        return STRONG
    if accuracy < t.needs_revision_below:
        return NEEDS_REVISION
    return DEVELOPING


def compute_topics(rows: list[dict[str, Any]], t: Thresholds) -> list[TopicStat]:
    """`rows` are per (attempt, topic) sums. Overall accuracy sets the label; the newest
    `recent_attempts` attempts are compared with the earlier ones for the trend."""
    by_topic: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_topic.setdefault(row["topic"], []).append(row)
    out: list[TopicStat] = []
    for topic, items in by_topic.items():
        items.sort(key=lambda r: (r["submitted_at"], str(r["attempt_id"])), reverse=True)
        awarded = sum(r["awarded"] for r in items)
        available = sum(r["available"] for r in items)
        answers = sum(r["answers"] for r in items)
        correct = sum(r["correct"] for r in items)
        recent, previous = items[: t.recent_attempts], items[t.recent_attempts :]
        recent_acc = _pct(sum(r["awarded"] for r in recent), sum(r["available"] for r in recent))
        prev_answers = sum(r["answers"] for r in previous)
        prev_acc = (
            _pct(sum(r["awarded"] for r in previous), sum(r["available"] for r in previous))
            if prev_answers >= t.min_answers
            else None
        )
        trend = None
        if recent_acc is not None and prev_acc is not None:
            delta = recent_acc - prev_acc
            trend = (
                "improving"
                if delta >= t.trend_delta
                else "declining"
                if delta <= -t.trend_delta
                else "steady"
            )
        accuracy = _pct(awarded, available)
        out.append(
            TopicStat(
                topic=topic,
                attempts=len(items),
                answers=answers,
                correct=correct,
                accuracy=accuracy,
                recent_accuracy=recent_acc,
                previous_accuracy=prev_acc,
                trend=trend,
                status=label_for(accuracy, answers, t),
                last_attempt_at=items[0]["submitted_at"],
            )
        )
    order = {NEEDS_REVISION: 0, DEVELOPING: 1, STRONG: 2, NOT_ENOUGH: 3}
    out.sort(
        key=lambda s: (order[s.status], s.accuracy if s.accuracy is not None else 101, s.topic)
    )
    return out


def compute_streaks(dates: list[date], today: date) -> tuple[int, int, date | None]:
    """(current, longest, last active day). A streak is consecutive local days with activity. The
    current streak survives until the end of the day after the last active day, so it is never
    reset just because today has not happened yet (no pressure, spec 3.3)."""
    days = sorted(set(dates))
    if not days:
        return 0, 0, None
    longest = run = 1
    for prev, cur in zip(days, days[1:], strict=False):
        run = run + 1 if cur - prev == timedelta(days=1) else 1
        longest = max(longest, run)
    last = days[-1]
    current = 0
    if last in (today, today - timedelta(days=1)):
        current = 1
        for i in range(len(days) - 1, 0, -1):
            if days[i] - days[i - 1] == timedelta(days=1):
                current += 1
            else:
                break
    return current, longest, last
