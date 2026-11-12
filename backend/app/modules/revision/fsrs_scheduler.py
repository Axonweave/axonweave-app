"""FSRS scheduling adapter (Phase 5, D-105 to D-107).

A thin, pure wrapper around the maintained `fsrs` package (py-fsrs, MIT): state + rating + now in,
new state out. It touches no database, clock, network or random source: the caller passes `now`,
and interval fuzzing (which uses `random`) is off by default so results are reproducible. The
algorithm itself is the library's; nothing here invents intervals.

The library has no "new" state, so a card that was never reviewed is the library's `Learning` state
with no stability. `CardState.state == "new"` marks it for the application and is mapped on the way
in and out.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from fsrs import Card, Scheduler
from fsrs import Rating as FsrsRating
from fsrs import State as FsrsState

# Names the scheduler configuration stored on rows and events (D-107). Bump when the default
# parameters, steps or library behaviour change; history keeps the version that produced it.
DEFAULT_SCHEDULER_VERSION = "fsrs6-default-1"

MIN_RETENTION = 0.7
MAX_RETENTION = 0.99
_FAR_FUTURE_DAYS = 36500


class Rating(StrEnum):
    AGAIN = "again"
    HARD = "hard"
    GOOD = "good"
    EASY = "easy"


_TO_FSRS_RATING = {
    Rating.AGAIN: FsrsRating.Again,
    Rating.HARD: FsrsRating.Hard,
    Rating.GOOD: FsrsRating.Good,
    Rating.EASY: FsrsRating.Easy,
}
_STATE_FROM_FSRS = {
    FsrsState.Learning: "learning",
    FsrsState.Review: "review",
    FsrsState.Relearning: "relearning",
}
_STATE_TO_FSRS = {
    "new": FsrsState.Learning,
    "learning": FsrsState.Learning,
    "review": FsrsState.Review,
    "relearning": FsrsState.Relearning,
}


class SchedulerError(ValueError):
    """Invalid state, rating or time passed to the scheduler."""


@dataclass(frozen=True)
class SchedulerConfig:
    """Everything that changes the schedule. `parameters=None` uses the library defaults
    (the 21 FSRS-6 weights); a stored per-user parameter set can be passed later with its own
    `version`."""

    desired_retention: float = 0.9
    learning_steps_minutes: tuple[int, ...] = (1, 10)
    relearning_steps_minutes: tuple[int, ...] = (10,)
    maximum_interval_days: int = _FAR_FUTURE_DAYS
    parameters: tuple[float, ...] | None = None
    enable_fuzzing: bool = False
    version: str = DEFAULT_SCHEDULER_VERSION

    def __post_init__(self) -> None:
        if not MIN_RETENTION <= self.desired_retention <= MAX_RETENTION:
            raise SchedulerError(
                f"desired_retention must be between {MIN_RETENTION} and {MAX_RETENTION}"
            )
        if self.maximum_interval_days < 1:
            raise SchedulerError("maximum_interval_days must be at least 1")
        if any(m < 1 for m in (*self.learning_steps_minutes, *self.relearning_steps_minutes)):
            raise SchedulerError("learning steps must be positive minutes")
        if not self.version or len(self.version) > 32:
            raise SchedulerError("version must be 1 to 32 characters")


@dataclass(frozen=True)
class CardState:
    """Scheduling state of one card. All datetimes are timezone-aware UTC."""

    state: str
    due: datetime
    step: int | None = None
    stability: float | None = None
    difficulty: float | None = None
    last_review: datetime | None = None
    repetitions: int = 0
    lapses: int = 0

    @classmethod
    def new(cls, due: datetime) -> "CardState":
        """A card never reviewed; it is due at `due` (normally its creation time)."""
        return cls(state="new", due=_utc(due))

    def to_json(self) -> dict[str, Any]:
        """JSON-safe form for `flashcard_reviews.previous_state` / `resulting_state`."""
        return {
            "state": self.state,
            "step": self.step,
            "stability": self.stability,
            "difficulty": self.difficulty,
            "due": self.due.isoformat(),
            "last_review": self.last_review.isoformat() if self.last_review else None,
            "repetitions": self.repetitions,
            "lapses": self.lapses,
        }

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> "CardState":
        try:
            last = data["last_review"]
            return cls(
                state=str(data["state"]),
                step=None if data["step"] is None else int(data["step"]),
                stability=None if data["stability"] is None else float(data["stability"]),
                difficulty=None if data["difficulty"] is None else float(data["difficulty"]),
                due=_utc(datetime.fromisoformat(str(data["due"]))),
                last_review=None if last is None else _utc(datetime.fromisoformat(str(last))),
                repetitions=int(data["repetitions"]),
                lapses=int(data["lapses"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise SchedulerError("invalid stored card state") from exc


@dataclass(frozen=True)
class ReviewOutcome:
    """Result of one review. `elapsed_days` is whole days since the previous review (0 for a first
    review); `scheduled_days` is whole days from `now` to the new due time (0 for a learning step
    that is due within the day); `retrievability` is the model's recall probability just before the
    review (None for a card never reviewed)."""

    state: CardState
    elapsed_days: int
    scheduled_days: int
    retrievability: float | None


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise SchedulerError("datetimes must be timezone-aware")
    return value.astimezone(UTC)


class FsrsScheduler:
    def __init__(self, config: SchedulerConfig | None = None) -> None:
        self.config = config or SchedulerConfig()
        kwargs: dict[str, Any] = {}
        if self.config.parameters is not None:
            kwargs["parameters"] = self.config.parameters
        try:
            self._scheduler = Scheduler(
                desired_retention=self.config.desired_retention,
                learning_steps=tuple(
                    timedelta(minutes=m) for m in self.config.learning_steps_minutes
                ),
                relearning_steps=tuple(
                    timedelta(minutes=m) for m in self.config.relearning_steps_minutes
                ),
                maximum_interval=self.config.maximum_interval_days,
                enable_fuzzing=self.config.enable_fuzzing,
                **kwargs,
            )
        except ValueError as exc:  # out-of-bounds parameters
            raise SchedulerError("invalid scheduler parameters") from exc

    @property
    def version(self) -> str:
        return self.config.version

    # ── mapping ───────────────────────────────────────────────────────────────────────────
    def _to_card(self, s: CardState) -> Card:
        if s.state not in _STATE_TO_FSRS:
            raise SchedulerError("unknown card state")
        if s.state == "new":
            if s.last_review is not None or s.stability is not None:
                raise SchedulerError("a new card has no review history")
        elif s.stability is None or s.difficulty is None or s.last_review is None:
            raise SchedulerError("a reviewed card needs stability, difficulty and last_review")
        if s.state in ("learning", "relearning") and s.step is None:
            raise SchedulerError("a learning card needs a step")
        return Card(
            card_id=0,  # unused: the library only needs some id; ours live in the database
            state=_STATE_TO_FSRS[s.state],
            step=None if s.state == "review" else s.step,
            stability=s.stability,
            difficulty=s.difficulty,
            due=_utc(s.due),
            last_review=None if s.last_review is None else _utc(s.last_review),
        )

    # ── operations ────────────────────────────────────────────────────────────────────────
    def review(
        self,
        state: CardState,
        rating: Rating,
        now: datetime,
        response_time_ms: int | None = None,
    ) -> ReviewOutcome:
        """Apply one rating. Early reviews (now < due) and late ones (now > due) are both handled
        by the library from `last_review`; a review earlier than the previous one is rejected."""
        now = _utc(now)
        if state.last_review is not None and now < state.last_review:
            raise SchedulerError("review time is before the previous review")
        if response_time_ms is not None and response_time_ms < 0:
            raise SchedulerError("response_time_ms must not be negative")
        try:
            fsrs_rating = _TO_FSRS_RATING[Rating(rating)]
        except ValueError as exc:
            raise SchedulerError("unknown rating") from exc

        card = self._to_card(state)
        retrievability = (
            None
            if state.state == "new"
            else self._scheduler.get_card_retrievability(card, current_datetime=now)
        )
        new_card, _log = self._scheduler.review_card(
            card, fsrs_rating, review_datetime=now, review_duration=response_time_ms
        )
        lapsed = state.state == "review" and rating == Rating.AGAIN
        new_state = CardState(
            state=_STATE_FROM_FSRS[new_card.state],
            due=_utc(new_card.due),
            step=new_card.step,
            stability=new_card.stability,
            difficulty=new_card.difficulty,
            last_review=now,
            repetitions=state.repetitions + 1,
            lapses=state.lapses + (1 if lapsed else 0),
        )
        elapsed = 0 if state.last_review is None else (now - state.last_review).days
        return ReviewOutcome(
            state=new_state,
            elapsed_days=elapsed,
            scheduled_days=max(0, (new_state.due - now).days),
            retrievability=retrievability,
        )

    def retrievability(self, state: CardState, now: datetime) -> float | None:
        """Predicted recall probability at `now`; None for a card never reviewed."""
        if state.state == "new":
            return None
        return self._scheduler.get_card_retrievability(self._to_card(state), _utc(now))

    def preview(self, state: CardState, now: datetime) -> dict[Rating, CardState]:
        """What each rating would produce, without recording anything (for interval labels)."""
        return {r: self.review(state, r, now).state for r in Rating}
