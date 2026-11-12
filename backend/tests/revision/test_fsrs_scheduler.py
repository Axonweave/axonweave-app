"""FsrsScheduler: pure adapter over py-fsrs (D-105 to D-107).

Two kinds of check: fixed vectors worked out from the FSRS-6 default parameters (so a library
upgrade that changes the maths is noticed), and equality with the library's own scheduler on random
but seeded review sequences (the adapter adds no scheduling logic of its own).
"""

import math
import random
from datetime import UTC, datetime, timedelta, timezone

import pytest
from fsrs import Card, Scheduler
from fsrs import Rating as FsrsRating
from fsrs import State as FsrsState
from fsrs.scheduler import DEFAULT_PARAMETERS

from app.modules.revision.fsrs_scheduler import (
    CardState,
    FsrsScheduler,
    Rating,
    SchedulerConfig,
    SchedulerError,
)

T0 = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
W = DEFAULT_PARAMETERS


def _sched(**kw: object) -> FsrsScheduler:
    return FsrsScheduler(SchedulerConfig(**kw))  # type: ignore[arg-type]


def test_first_review_vectors_for_every_rating() -> None:
    sch = _sched()
    for rating, idx in ((Rating.AGAIN, 0), (Rating.HARD, 1), (Rating.GOOD, 2), (Rating.EASY, 3)):
        out = sch.review(CardState.new(T0), rating, T0)
        assert out.state.stability == pytest.approx(W[idx])
        grade = idx + 1
        assert out.state.difficulty == pytest.approx(
            min(10.0, max(1.0, W[4] - math.e ** (W[5] * (grade - 1)) + 1))
        )
        assert out.state.repetitions == 1
        assert out.state.lapses == 0
        assert out.state.last_review == T0
        assert out.elapsed_days == 0
        assert out.retrievability is None


def test_learning_steps_then_graduation_and_interval() -> None:
    sch = _sched()
    s = CardState.new(T0)
    out = sch.review(s, Rating.GOOD, T0)
    assert (out.state.state, out.state.step) == ("learning", 1)
    assert out.state.due == T0 + timedelta(minutes=10)
    assert out.scheduled_days == 0

    out2 = sch.review(out.state, Rating.GOOD, out.state.due)
    assert out2.state.state == "review"
    assert out2.state.step is None
    assert out2.scheduled_days == 2  # interval for stability 2.3065 at 90 percent retention
    assert out2.state.due == out.state.due + timedelta(days=2)

    out3 = sch.review(out2.state, Rating.GOOD, out2.state.due)
    assert out3.state.stability == pytest.approx(10.971048263, rel=1e-6)
    assert out3.scheduled_days == 11
    assert out3.elapsed_days == 2
    # at the due date predicted recall is about the desired retention (the interval is rounded)
    assert out3.retrievability == pytest.approx(0.9, abs=0.02)


def test_again_on_a_review_card_is_a_lapse_and_relearns() -> None:
    sch = _sched()
    s = _graduated(sch)
    out = sch.review(s, Rating.AGAIN, s.due)
    assert out.state.state == "relearning"
    assert out.state.lapses == s.lapses + 1
    assert out.state.stability is not None and s.stability is not None
    assert out.state.stability < s.stability
    assert out.state.due == s.due + timedelta(minutes=10)


def test_again_while_learning_is_not_a_lapse() -> None:
    out = _sched().review(CardState.new(T0), Rating.AGAIN, T0)
    assert out.state.state == "learning"
    assert out.state.lapses == 0


def test_rating_order_gives_longer_intervals() -> None:
    sch = _sched()
    s = _graduated(sch)
    due = {r: sch.review(s, r, s.due).state.due for r in (Rating.HARD, Rating.GOOD, Rating.EASY)}
    assert due[Rating.HARD] < due[Rating.GOOD] < due[Rating.EASY]


def test_early_review_is_accepted_and_differs_from_on_time() -> None:
    sch = _sched()
    s = _graduated(sch)
    early_time = s.due - timedelta(days=1)
    assert s.last_review is not None and early_time > s.last_review
    early = sch.review(s, Rating.GOOD, early_time)
    on_time = sch.review(s, Rating.GOOD, s.due)
    assert early.retrievability is not None and on_time.retrievability is not None
    assert early.retrievability > on_time.retrievability
    assert early.state.stability is not None and on_time.state.stability is not None
    assert early.state.stability < on_time.state.stability  # less proven recall, less growth
    assert early.state.last_review == early_time


def test_overdue_review_uses_real_elapsed_time() -> None:
    sch = _sched()
    s = _graduated(sch)
    late = sch.review(s, Rating.GOOD, s.due + timedelta(days=30))
    on_time = sch.review(s, Rating.GOOD, s.due)
    assert late.elapsed_days > on_time.elapsed_days
    assert late.retrievability is not None and on_time.retrievability is not None
    assert late.retrievability < on_time.retrievability


def test_target_retention_changes_interval_in_the_right_direction() -> None:
    low, default, high = (_sched(desired_retention=r) for r in (0.8, 0.9, 0.95))
    s = _graduated(default)

    def days(sch: FsrsScheduler) -> int:
        return sch.review(s, Rating.GOOD, s.due).scheduled_days

    assert days(low) > days(default) > days(high)


@pytest.mark.parametrize("bad", [0.5, 0.69, 0.995, 1.0, 0.0])
def test_retention_out_of_range_is_rejected(bad: float) -> None:
    with pytest.raises(SchedulerError):
        SchedulerConfig(desired_retention=bad)


def test_invalid_parameters_and_steps_are_rejected() -> None:
    with pytest.raises(SchedulerError):
        FsrsScheduler(SchedulerConfig(parameters=(1.0, 2.0)))
    with pytest.raises(SchedulerError):
        SchedulerConfig(learning_steps_minutes=(0,))
    with pytest.raises(SchedulerError):
        SchedulerConfig(maximum_interval_days=0)
    with pytest.raises(SchedulerError):
        SchedulerConfig(version="")


def test_maximum_interval_is_respected() -> None:
    sch = _sched(maximum_interval_days=5)
    s = _graduated(sch)
    for _ in range(6):
        out = sch.review(s, Rating.EASY, s.due)
        assert out.scheduled_days <= 5
        s = out.state


def test_deterministic_same_input_same_output() -> None:
    a = _sched()
    b = _sched()
    s = _graduated(a)
    assert a.review(s, Rating.GOOD, s.due) == b.review(s, Rating.GOOD, s.due)
    assert a.review(s, Rating.GOOD, s.due) == a.review(s, Rating.GOOD, s.due)


def test_input_state_is_not_mutated_and_preview_records_nothing() -> None:
    sch = _sched()
    s = _graduated(sch)
    before = s.to_json()
    preview = sch.preview(s, s.due)
    assert set(preview) == set(Rating)
    assert s.to_json() == before


def test_matches_the_library_directly_on_seeded_sequences() -> None:
    """The adapter must equal the library's own scheduler for the same inputs (no extra logic)."""
    rng = random.Random(1234)
    sch = _sched()
    lib = Scheduler(enable_fuzzing=False)
    for _ in range(25):
        state = CardState.new(T0)
        card = Card(card_id=1, due=T0)
        now = T0
        for _ in range(12):
            rating = rng.choice(list(Rating))
            now = now + timedelta(
                minutes=rng.choice([0, 5, 30, 600, 3000, 60 * 24 * 9, 60 * 24 * 40])
            )
            out = sch.review(state, rating, now)
            card, _log = lib.review_card(card, FsrsRating[rating.name.capitalize()], now)
            assert out.state.stability == card.stability
            assert out.state.difficulty == card.difficulty
            assert out.state.due == card.due
            assert out.state.step == card.step
            assert (
                out.state.state
                == {
                    FsrsState.Learning: "learning",
                    FsrsState.Review: "review",
                    FsrsState.Relearning: "relearning",
                }[card.state]
            )
            state = out.state


def test_state_json_round_trip() -> None:
    sch = _sched()
    s = _graduated(sch)
    assert CardState.from_json(s.to_json()) == s
    new = CardState.new(T0)
    assert CardState.from_json(new.to_json()) == new


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"state": "review"},
        {
            "state": "review",
            "step": None,
            "stability": "abc",
            "difficulty": 1,
            "due": T0.isoformat(),
            "last_review": None,
            "repetitions": 1,
            "lapses": 0,
        },
        {
            "state": "review",
            "step": None,
            "stability": 1,
            "difficulty": 1,
            "due": "not a date",
            "last_review": None,
            "repetitions": 1,
            "lapses": 0,
        },
    ],
)
def test_invalid_stored_state_is_rejected(data: dict[str, object]) -> None:
    with pytest.raises(SchedulerError):
        CardState.from_json(data)


def test_invalid_states_and_inputs_are_rejected() -> None:
    sch = _sched()
    with pytest.raises(SchedulerError):  # unknown state
        sch.review(CardState(state="bogus", due=T0), Rating.GOOD, T0)
    with pytest.raises(SchedulerError):  # reviewed card without memory state
        sch.review(CardState(state="review", due=T0), Rating.GOOD, T0)
    with pytest.raises(SchedulerError):  # new card with history
        sch.review(CardState(state="new", due=T0, last_review=T0), Rating.GOOD, T0)
    with pytest.raises(SchedulerError):  # naive datetime
        sch.review(CardState.new(T0), Rating.GOOD, datetime(2026, 1, 1))  # noqa: DTZ001
    with pytest.raises(SchedulerError):  # unknown rating
        sch.review(CardState.new(T0), "meh", T0)  # type: ignore[arg-type]
    with pytest.raises(SchedulerError):  # negative response time
        sch.review(CardState.new(T0), Rating.GOOD, T0, response_time_ms=-1)
    s = _graduated(sch)
    assert s.last_review is not None
    with pytest.raises(SchedulerError):  # before the previous review
        sch.review(s, Rating.GOOD, s.last_review - timedelta(seconds=1))


def test_non_utc_input_is_normalised_to_utc() -> None:
    sch = _sched()
    ist = timezone(timedelta(hours=5, minutes=30))
    out = sch.review(CardState.new(T0), Rating.GOOD, T0.astimezone(ist))
    assert out.state.due.utcoffset() == timedelta(0)
    assert out.state.due == T0 + timedelta(minutes=10)


def test_retrievability_decays_over_time() -> None:
    sch = _sched()
    s = _graduated(sch)
    assert s.last_review is not None
    r0 = sch.retrievability(s, s.last_review)
    r1 = sch.retrievability(s, s.last_review + timedelta(days=5))
    r2 = sch.retrievability(s, s.last_review + timedelta(days=60))
    assert r0 == pytest.approx(1.0)
    assert r0 is not None and r1 is not None and r2 is not None
    assert r0 > r1 > r2 > 0
    assert sch.retrievability(CardState.new(T0), T0) is None


def test_scheduler_version_is_exposed_for_storage() -> None:
    assert _sched().version == "fsrs6-default-1"
    assert _sched(version="custom-7").version == "custom-7"


def _graduated(sch: FsrsScheduler) -> CardState:
    """A card that finished its learning steps (state 'review')."""
    s = CardState.new(T0)
    s = sch.review(s, Rating.GOOD, T0).state
    s = sch.review(s, Rating.GOOD, s.due).state
    assert s.state == "review"
    return s
