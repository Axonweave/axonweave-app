"""Phase 5 M3: spaced repetition API (scheduling, review, suspend, sessions, timezones, isolation).

FakeProvider only: no network, no cost. The clock is pinned by patching the service's `_now`.
"""

import asyncio
import uuid
from collections.abc import Callable, Generator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.main import app
from app.models.revision import FlashcardReview, FlashcardScheduling, RevisionSession
from app.models.user_profile import UserProfile
from tests.ai.test_provider_layer import make_settings
from tests.conftest import _TestSessionLocal
from tests.retrieval.test_search import Actor
from tests.study.conftest import Harness
from tests.study.test_flashcards import card, make_deck
from tests.test_closeout_users_config import _call

NOW = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)
MANY = [card(f"Question number {i}?", f"Answer number {i}.") for i in range(6)]


@pytest.fixture(autouse=True)
def clock(monkeypatch: pytest.MonkeyPatch) -> list[datetime]:
    """Pinned time; tests move it by appending."""
    now = [NOW]
    monkeypatch.setattr("app.modules.revision.service._now", lambda: now[-1])
    return now


@pytest.fixture
def cfg() -> Generator[Callable[..., None]]:
    """Override the settings the revision routes read (the real dependency, not the AI runtime)."""

    def apply(**values: Any) -> None:
        app.dependency_overrides[get_settings] = lambda: make_settings(**values)

    yield apply
    app.dependency_overrides.pop(get_settings, None)


async def deck(
    client: AsyncClient,
    study: Harness,
    who: Actor,
    db: AsyncSession,
    cards: list[dict[str, Any]] | None = None,
) -> list[str]:
    _, _, payload = await make_deck(client, study, who, db, cards or MANY[:3])
    return [c["id"] for c in payload["cards"]]


def review_path(card_id: str) -> str:
    return f"/study/flashcards/cards/{card_id}/review"


async def rev(
    client: AsyncClient,
    who: Actor,
    card_id: str,
    rating: str = "good",
    key: str | None = None,
    **extra: Any,
) -> Any:
    body = {"rating": rating, "idempotency_key": key or f"k-{uuid.uuid4().hex}", **extra}
    return await _call(client, who, "POST", review_path(card_id), json=body)


async def summary(client: AsyncClient, who: Actor, query: str = "") -> dict[str, Any]:
    resp = await _call(client, who, "GET", f"/revision/summary{query}")
    assert resp.status_code == 200, resp.text
    data: dict[str, Any] = resp.json()["data"]
    return data


async def listing(client: AsyncClient, who: Actor, path: str) -> dict[str, Any]:
    resp = await _call(client, who, "GET", path)
    assert resp.status_code == 200, resp.text
    data: dict[str, Any] = resp.json()["data"]
    return data


async def set_due(card_id: str, due: datetime, **values: Any) -> None:
    async with _TestSessionLocal() as s:
        await s.execute(
            update(FlashcardScheduling)
            .where(FlashcardScheduling.flashcard_id == uuid.UUID(card_id))
            .values(due_at=due, **values)
        )
        await s.commit()


class TestScheduling:
    async def test_scheduling_rows_are_created_lazily(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        ids = await deck(client, study, alice, db_session)
        async with _TestSessionLocal() as s:
            assert (await s.execute(select(FlashcardScheduling))).scalars().all() == []
        data = await summary(client, alice)
        assert data["total_cards"] == 3 and data["new"] == 3 and data["due_today"] == 0
        async with _TestSessionLocal() as s:
            rows = (await s.execute(select(FlashcardScheduling))).scalars().all()
        assert {str(r.flashcard_id) for r in rows} == set(ids) and {r.state for r in rows} == {
            "new"
        }
        await summary(client, alice)  # idempotent: no duplicates
        async with _TestSessionLocal() as s:
            assert len((await s.execute(select(FlashcardScheduling))).scalars().all()) == 3

    async def test_new_cards_appear_in_new_not_due(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        await deck(client, study, alice, db_session)
        assert (await listing(client, alice, "/revision/new"))["total"] == 3
        assert (await listing(client, alice, "/revision/due"))["total"] == 0
        assert (await listing(client, alice, "/revision/overdue"))["total"] == 0

    @pytest.mark.parametrize(
        ("rating", "state"),
        [("again", "learning"), ("hard", "learning"), ("good", "learning"), ("easy", "review")],
    )
    async def test_first_review_with_every_rating(
        self,
        client: AsyncClient,
        study: Harness,
        alice: Actor,
        db_session: AsyncSession,
        rating: str,
        state: str,
    ) -> None:
        ids = await deck(client, study, alice, db_session)
        resp = await rev(client, alice, ids[0], rating)
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["duplicate"] is False and data["schedule"]["state"] == state
        assert data["schedule"]["repetitions"] == 1
        assert datetime.fromisoformat(data["schedule"]["due_at"]) > NOW
        assert data["review"]["previous_state"]["state"] == "new"
        assert data["review"]["resulting_state"]["state"] == state
        assert data["review"]["scheduler_version"] == data["schedule"]["scheduler_version"]

    async def test_learning_card_is_due_later_the_same_day(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        ids = await deck(client, study, alice, db_session)
        await rev(client, alice, ids[0], "good")  # first learning step: minutes
        due = await listing(client, alice, "/revision/due")
        assert due["total"] == 1 and due["items"][0]["card"]["id"] == ids[0]
        assert (
            due["timezone"] == "UTC" and due["items"][0]["schedule"]["retrievability"] is not None
        )

    async def test_later_reviews_grow_the_interval(
        self,
        client: AsyncClient,
        study: Harness,
        alice: Actor,
        db_session: AsyncSession,
        clock: list[datetime],
    ) -> None:
        ids = await deck(client, study, alice, db_session)
        first = (await rev(client, alice, ids[0], "easy")).json()["data"]["schedule"]
        clock.append(datetime.fromisoformat(first["due_at"]))
        second = (await rev(client, alice, ids[0], "good")).json()["data"]["schedule"]
        assert second["scheduled_days"] > first["scheduled_days"] and second["repetitions"] == 2
        assert second["stability"] > first["stability"]

    async def test_a_lapse_is_counted(
        self,
        client: AsyncClient,
        study: Harness,
        alice: Actor,
        db_session: AsyncSession,
        clock: list[datetime],
    ) -> None:
        ids = await deck(client, study, alice, db_session)
        first = (await rev(client, alice, ids[0], "easy")).json()["data"]["schedule"]
        clock.append(datetime.fromisoformat(first["due_at"]))
        lapsed = (await rev(client, alice, ids[0], "again")).json()["data"]["schedule"]
        assert lapsed["state"] == "relearning" and lapsed["lapses"] == 1

    async def test_overdue_and_early_reviews(
        self,
        client: AsyncClient,
        study: Harness,
        alice: Actor,
        db_session: AsyncSession,
        clock: list[datetime],
    ) -> None:
        ids = await deck(client, study, alice, db_session)
        first = (await rev(client, alice, ids[0], "easy")).json()["data"]["schedule"]
        due_at = datetime.fromisoformat(first["due_at"])
        # reviewed long after it was due: overdue lists show it, the review still works
        clock.append(due_at + timedelta(days=5))
        assert (await listing(client, alice, "/revision/overdue"))["total"] == 1
        late = await rev(client, alice, ids[0], "good")
        assert late.status_code == 200 and late.json()["data"]["review"]["elapsed_days"] >= 5
        # reviewed before it is due: allowed, not rejected
        early_at = datetime.fromisoformat(late.json()["data"]["schedule"]["due_at"]) - timedelta(
            days=2
        )
        clock.append(early_at)
        early = await rev(client, alice, ids[0], "good")
        assert early.status_code == 200

    async def test_schedule_route_and_history(
        self,
        client: AsyncClient,
        study: Harness,
        alice: Actor,
        db_session: AsyncSession,
        clock: list[datetime],
    ) -> None:
        ids = await deck(client, study, alice, db_session)
        for minutes, rating in enumerate(("good", "hard", "again")):
            clock.append(NOW + timedelta(minutes=minutes))
            assert (await rev(client, alice, ids[0], rating)).status_code == 200
        sched = await _call(client, alice, "GET", f"/study/flashcards/cards/{ids[0]}/schedule")
        assert sched.status_code == 200 and sched.json()["data"]["repetitions"] == 3
        hist = await listing(
            client, alice, f"/study/flashcards/cards/{ids[0]}/review-history?limit=2"
        )
        assert hist["total"] == 3 and len(hist["items"]) == 2
        assert hist["items"][0]["rating"] == "again"  # newest first
        assert hist["items"][0]["previous_state"]["repetitions"] == 2

    async def test_corrupt_stored_state_is_reported_not_guessed(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        ids = await deck(client, study, alice, db_session)
        await summary(client, alice)
        await set_due(ids[0], NOW, state="review", stability=None, difficulty=None)
        resp = await rev(client, alice, ids[0], "good")
        assert resp.status_code == 409 and resp.json()["error"]["code"] == "SCHEDULE_STATE_INVALID"
        async with _TestSessionLocal() as s:
            assert (await s.execute(select(FlashcardReview))).scalars().all() == []


class TestIdempotencyAndConcurrency:
    async def test_retry_with_the_same_key_returns_the_stored_event(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        ids = await deck(client, study, alice, db_session)
        first = (await rev(client, alice, ids[0], "good", key="retry-key-1")).json()["data"]
        again = (await rev(client, alice, ids[0], "good", key="retry-key-1")).json()["data"]
        assert again["duplicate"] is True and again["review"]["id"] == first["review"]["id"]
        async with _TestSessionLocal() as s:
            assert len((await s.execute(select(FlashcardReview))).scalars().all()) == 1
        sched = await _call(client, alice, "GET", f"/study/flashcards/cards/{ids[0]}/schedule")
        assert sched.json()["data"]["repetitions"] == 1  # not reviewed twice

    async def test_a_key_cannot_be_reused_on_another_card(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        ids = await deck(client, study, alice, db_session)
        await rev(client, alice, ids[0], key="shared-key-1")
        resp = await rev(client, alice, ids[1], key="shared-key-1")
        assert resp.status_code == 409 and resp.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"

    async def test_same_key_in_parallel_reviews_once(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        ids = await deck(client, study, alice, db_session)
        a, b = await asyncio.gather(
            rev(client, alice, ids[0], "good", key="parallel-key-1"),
            rev(client, alice, ids[0], "good", key="parallel-key-1"),
        )
        assert a.status_code == 200 and b.status_code == 200
        assert sorted([a.json()["data"]["duplicate"], b.json()["data"]["duplicate"]]) == [
            False,
            True,
        ]
        async with _TestSessionLocal() as s:
            assert len((await s.execute(select(FlashcardReview))).scalars().all()) == 1

    async def test_different_keys_in_parallel_apply_in_sequence(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        ids = await deck(client, study, alice, db_session)
        a, b = await asyncio.gather(
            rev(client, alice, ids[0], "good"), rev(client, alice, ids[0], "good")
        )
        assert a.status_code == 200 and b.status_code == 200
        sched = await _call(client, alice, "GET", f"/study/flashcards/cards/{ids[0]}/schedule")
        assert sched.json()["data"]["repetitions"] == 2

    async def test_keys_are_per_user(
        self,
        client: AsyncClient,
        study: Harness,
        alice: Actor,
        bob: Actor,
        db_session: AsyncSession,
    ) -> None:
        mine = await deck(client, study, alice, db_session)
        theirs = await deck(client, study, bob, db_session)
        assert (await rev(client, alice, mine[0], key="same-key-xyz")).status_code == 200
        assert (await rev(client, bob, theirs[0], key="same-key-xyz")).status_code == 200

    @pytest.mark.parametrize(
        "body",
        [
            {"rating": "great", "idempotency_key": "valid-key-1"},
            {"rating": "good"},
            {"rating": "good", "idempotency_key": "short"},
            {"rating": "good", "idempotency_key": "bad key with spaces"},
            {"rating": "good", "idempotency_key": "valid-key-1", "response_time_ms": -1},
            {"rating": "good", "idempotency_key": "valid-key-1", "extra": 1},
        ],
    )
    async def test_review_input_is_validated(
        self,
        client: AsyncClient,
        study: Harness,
        alice: Actor,
        db_session: AsyncSession,
        body: dict[str, Any],
    ) -> None:
        ids = await deck(client, study, alice, db_session)
        resp = await _call(client, alice, "POST", review_path(ids[0]), json=body)
        assert resp.status_code == 422

    async def test_review_rate_limit(
        self,
        client: AsyncClient,
        study: Harness,
        alice: Actor,
        db_session: AsyncSession,
        cfg: Callable[..., None],
    ) -> None:
        ids = await deck(client, study, alice, db_session)
        cfg(revision_reviews_per_minute_per_user=2)
        codes = [(await rev(client, alice, ids[0])).status_code for _ in range(3)]
        assert codes == [200, 200, 429]


class TestSuspend:
    async def test_suspended_cards_are_not_reviewed_or_listed(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        ids = await deck(client, study, alice, db_session)
        resp = await _call(client, alice, "PATCH", f"/study/flashcards/cards/{ids[0]}/suspend")
        assert resp.status_code == 200 and resp.json()["data"]["suspended"] is True
        blocked = await rev(client, alice, ids[0])
        assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "CARD_SUSPENDED"
        assert (await listing(client, alice, "/revision/new"))["total"] == 2
        assert (await listing(client, alice, "/revision/cards?bucket=suspended"))["total"] == 1
        assert (await summary(client, alice))["suspended"] == 1
        back = await _call(client, alice, "PATCH", f"/study/flashcards/cards/{ids[0]}/unsuspend")
        assert back.json()["data"]["suspended"] is False
        assert (await rev(client, alice, ids[0])).status_code == 200


class TestTimezones:
    async def _zone(self, who: Actor, name: str) -> None:
        async with _TestSessionLocal() as s:
            await s.execute(
                update(UserProfile).where(UserProfile.user_id == who.uid).values(timezone=name)  # type: ignore[attr-defined]
            )
            await s.commit()

    async def test_due_today_follows_the_users_local_day(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        ids = await deck(client, study, alice, db_session)
        await rev(client, alice, ids[0], "easy")
        # 19:00 UTC: still today in UTC, but 00:30 tomorrow in Asia/Kolkata (UTC+5:30)
        await set_due(ids[0], datetime(2026, 3, 10, 19, 0, tzinfo=UTC))
        assert (await summary(client, alice))["due_today"] == 1
        await self._zone(alice, "Asia/Kolkata")
        data = await summary(client, alice)
        assert data["due_today"] == 0 and data["timezone"] == "Asia/Kolkata"
        assert sum(day["count"] for day in data["upcoming"]) == 1
        assert data["upcoming"][0]["date"] == "2026-03-11"

    async def test_dst_day_bounds(
        self,
        client: AsyncClient,
        study: Harness,
        alice: Actor,
        db_session: AsyncSession,
        clock: list,
    ) -> None:
        await deck(client, study, alice, db_session)
        await self._zone(alice, "America/New_York")
        clock.append(datetime(2026, 3, 8, 12, 0, tzinfo=UTC))  # US spring-forward day: 23 hours
        due = await listing(client, alice, "/revision/due")
        start = datetime.fromisoformat(due["day_start"])
        end = datetime.fromisoformat(due["day_end"])
        assert end - start == timedelta(hours=23)

    async def test_an_unknown_zone_falls_back_to_utc(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        await deck(client, study, alice, db_session)
        await self._zone(alice, "Not/AZone")
        assert (await summary(client, alice))["timezone"] == "UTC"


class TestSummary:
    async def test_summary_counts_and_daily_completion(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        ids = await deck(client, study, alice, db_session, MANY[:4])
        await rev(client, alice, ids[0], "good")
        await rev(client, alice, ids[1], "easy")
        data = await summary(client, alice)
        assert data["total_cards"] == 4 and data["reviewed_today"] == 2 and data["new"] == 2
        assert data["learning"] == 1 and data["review"] == 1 and data["due_today"] == 1
        assert data["daily_completion"] == pytest.approx(2 / 3, abs=1e-3)
        assert data["new_cards_remaining_today"] == 18
        assert len(data["recent"]) == 2 and len(data["upcoming"]) == 7
        assert data["desired_retention"] == 0.9
        assert data["subjects"][0]["total"] == 4

    async def test_empty_account_has_empty_numbers_not_invented_ones(
        self, client: AsyncClient, study: Harness, alice: Actor
    ) -> None:
        data = await summary(client, alice)
        assert data["total_cards"] == 0 and data["daily_completion"] is None
        assert data["recent"] == [] and data["subjects"] == []


class TestSessions:
    async def test_session_lifecycle(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        ids = await deck(client, study, alice, db_session)
        resp = await _call(client, alice, "POST", "/revision/sessions", json={})
        assert resp.status_code == 201, resp.text
        session = resp.json()["data"]
        assert session["total_cards"] == 3 and session["status"] == "active"
        again = await _call(client, alice, "POST", "/revision/sessions", json={})
        assert again.status_code == 200 and again.json()["data"]["id"] == session["id"]
        assert again.json()["data"]["resumed"] is True
        sid = session["id"]
        for rating in ("good", "again", "easy"):
            r = await rev(
                client, alice, ids[["good", "again", "easy"].index(rating)], rating, session_id=sid
            )
            assert r.status_code == 200, r.text
        detail = (await _call(client, alice, "GET", f"/revision/sessions/{sid}")).json()["data"]
        assert detail["reviewed_cards"] == 3 and all(c["reviewed"] for c in detail["cards"])
        done = await _call(client, alice, "POST", f"/revision/sessions/{sid}/complete")
        assert done.status_code == 200 and done.json()["data"]["status"] == "completed"
        again = await _call(client, alice, "POST", f"/revision/sessions/{sid}/complete")
        assert again.status_code == 200  # idempotent
        final = (await _call(client, alice, "GET", f"/revision/sessions/{sid}")).json()["data"]
        assert final["summary"]["rating_distribution"] == {
            "again": 1,
            "hard": 0,
            "good": 1,
            "easy": 1,
        }
        assert final["summary"]["next_due_at"] is not None
        late = await rev(client, alice, ids[0], "good", session_id=sid)
        assert late.status_code == 409 and late.json()["error"]["code"] == "SESSION_NOT_ACTIVE"
        listed = await listing(client, alice, "/revision/sessions?status=completed")
        assert listed["total"] == 1

    async def test_two_reviews_of_one_card_count_once(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        ids = await deck(client, study, alice, db_session)
        sid = (await _call(client, alice, "POST", "/revision/sessions", json={})).json()["data"][
            "id"
        ]
        await rev(client, alice, ids[0], "again", session_id=sid)
        await rev(client, alice, ids[0], "good", session_id=sid)
        detail = (await _call(client, alice, "GET", f"/revision/sessions/{sid}")).json()["data"]
        assert detail["reviewed_cards"] == 1

    async def test_card_outside_the_session_is_rejected(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        ids = await deck(client, study, alice, db_session, MANY[:4])
        resp = await _call(client, alice, "POST", "/revision/sessions", json={"limit": 2})
        sid = resp.json()["data"]["id"]
        assert resp.json()["data"]["total_cards"] == 2
        detail = (await _call(client, alice, "GET", f"/revision/sessions/{sid}")).json()["data"]
        inside = {c["card"]["id"] for c in detail["cards"]}
        outside = next(i for i in ids if i not in inside)
        bad = await rev(client, alice, outside, session_id=sid)
        assert bad.status_code == 422 and bad.json()["error"]["code"] == "CARD_NOT_IN_SESSION"

    async def test_new_card_cap_limits_the_session(
        self,
        client: AsyncClient,
        study: Harness,
        alice: Actor,
        db_session: AsyncSession,
        cfg: Callable[..., None],
    ) -> None:
        await deck(client, study, alice, db_session, MANY[:5])
        cfg(revision_new_cards_per_day=2)
        resp = await _call(client, alice, "POST", "/revision/sessions", json={})
        assert resp.json()["data"]["total_cards"] == 2
        no_new = await _call(
            client, alice, "POST", "/revision/sessions/00000000-0000-0000-0000-000000000000/abandon"
        )
        assert no_new.status_code == 404

    async def test_nothing_due_is_a_clear_409(
        self, client: AsyncClient, study: Harness, alice: Actor
    ) -> None:
        resp = await _call(client, alice, "POST", "/revision/sessions", json={})
        assert resp.status_code == 409 and resp.json()["error"]["code"] == "NOTHING_DUE"

    async def test_stale_sessions_are_closed_and_replaced(
        self,
        client: AsyncClient,
        study: Harness,
        alice: Actor,
        db_session: AsyncSession,
        clock: list[datetime],
    ) -> None:
        await deck(client, study, alice, db_session)
        first = (await _call(client, alice, "POST", "/revision/sessions", json={})).json()["data"]
        clock.append(NOW + timedelta(hours=5))  # idle far longer than the 120 minute limit
        fresh = await _call(client, alice, "POST", "/revision/sessions", json={})
        assert fresh.status_code == 201 and fresh.json()["data"]["id"] != first["id"]
        old = (await _call(client, alice, "GET", f"/revision/sessions/{first['id']}")).json()[
            "data"
        ]
        assert old["status"] == "abandoned"

    async def test_abandon(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        await deck(client, study, alice, db_session)
        sid = (await _call(client, alice, "POST", "/revision/sessions", json={})).json()["data"][
            "id"
        ]
        gone = await _call(client, alice, "POST", f"/revision/sessions/{sid}/abandon")
        assert gone.status_code == 200 and gone.json()["data"]["status"] == "abandoned"
        again = await _call(client, alice, "POST", f"/revision/sessions/{sid}/abandon")
        assert again.status_code == 200
        done = await _call(client, alice, "POST", f"/revision/sessions/{sid}/complete")
        assert done.status_code == 409
        async with _TestSessionLocal() as s:
            row = (await s.execute(select(RevisionSession))).scalar_one()
        assert row.status == "abandoned"

    async def test_deleted_cards_are_skipped(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        ids = await deck(client, study, alice, db_session)
        sid = (await _call(client, alice, "POST", "/revision/sessions", json={})).json()["data"][
            "id"
        ]
        await rev(client, alice, ids[0])
        assert (
            await _call(client, alice, "DELETE", f"/study/flashcards/cards/{ids[0]}")
        ).status_code in (
            200,
            204,
        )
        detail = (await _call(client, alice, "GET", f"/revision/sessions/{sid}")).json()["data"]
        assert len(detail["cards"]) == 2
        async with _TestSessionLocal() as s:  # scheduling and reviews of the deleted card are gone
            left = (await s.execute(select(FlashcardScheduling))).scalars().all()
            assert str(ids[0]) not in {str(r.flashcard_id) for r in left}
            assert (await s.execute(select(FlashcardReview))).scalars().all() == []


class TestIsolation:
    async def test_other_users_cards_and_sessions_are_404(
        self,
        client: AsyncClient,
        study: Harness,
        alice: Actor,
        bob: Actor,
        db_session: AsyncSession,
    ) -> None:
        ids = await deck(client, study, alice, db_session)
        sid = (await _call(client, alice, "POST", "/revision/sessions", json={})).json()["data"][
            "id"
        ]
        card_paths = [
            ("GET", f"/study/flashcards/cards/{ids[0]}/schedule"),
            ("PATCH", f"/study/flashcards/cards/{ids[0]}/suspend"),
            ("PATCH", f"/study/flashcards/cards/{ids[0]}/unsuspend"),
            ("GET", f"/study/flashcards/cards/{ids[0]}/review-history"),
        ]
        for method, path in card_paths:
            assert (await _call(client, bob, method, path)).status_code == 404, path
        denied = await rev(client, bob, ids[0])
        assert denied.status_code == 404
        for method, path in [
            ("GET", f"/revision/sessions/{sid}"),
            ("POST", f"/revision/sessions/{sid}/complete"),
            ("POST", f"/revision/sessions/{sid}/abandon"),
        ]:
            assert (await _call(client, bob, method, path)).status_code == 404, path
        mine = await rev(client, alice, ids[0])
        assert mine.status_code == 200
        # reviewing in someone else's session is a 404 too, and nothing was recorded for bob
        theirs = await deck(client, study, bob, db_session)
        cross = await rev(client, bob, theirs[0], session_id=sid)
        assert cross.status_code == 404
        async with _TestSessionLocal() as s:
            reviews = (await s.execute(select(FlashcardReview))).scalars().all()
        assert len(reviews) == 1

    async def test_lists_only_contain_the_callers_cards(
        self,
        client: AsyncClient,
        study: Harness,
        alice: Actor,
        bob: Actor,
        db_session: AsyncSession,
    ) -> None:
        await deck(client, study, alice, db_session)
        assert (await listing(client, bob, "/revision/new"))["total"] == 0
        assert (await summary(client, bob))["total_cards"] == 0
        assert (await listing(client, bob, f"/revision/cards?subject_id={uuid.uuid4()}"))[
            "total"
        ] == 0
        assert (await _call(client, bob, "POST", "/revision/sessions", json={})).status_code == 409

    @pytest.mark.parametrize("query", ["limit=0", "limit=101", "offset=-1", "bucket=nope"])
    async def test_list_input_is_validated(
        self, client: AsyncClient, study: Harness, alice: Actor, query: str
    ) -> None:
        resp = await _call(client, alice, "GET", f"/revision/cards?{query}")
        assert resp.status_code == 422
