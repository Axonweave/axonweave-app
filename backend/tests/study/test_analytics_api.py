"""Phase 5 M5: learning analytics (overview, quizzes, subjects, topics, revision activity, calendar,
streaks, validation, isolation). FakeProvider only: no network, no cost."""

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.analytics.logic import Thresholds, compute_streaks, compute_topics
from tests.retrieval.test_search import Actor
from tests.study.conftest import Harness
from tests.study.test_quiz_assessment import new_quiz, run_attempt
from tests.study.test_revision_api import deck, rev
from tests.test_closeout_users_config import _call


async def get(client: AsyncClient, who: Actor, path: str) -> dict[str, Any]:
    resp = await _call(client, who, "GET", f"/analytics/{path}")
    assert resp.status_code == 200, resp.text
    data: dict[str, Any] = resp.json()["data"]
    return data


def d(day: str) -> date:
    return date.fromisoformat(day)


class TestPureLogic:
    def test_streaks_empty(self) -> None:
        assert compute_streaks([], d("2026-03-10")) == (0, 0, None)

    def test_streak_counts_consecutive_days_and_grace(self) -> None:
        days = [d("2026-03-07"), d("2026-03-08"), d("2026-03-09")]
        assert compute_streaks(days, d("2026-03-10")) == (3, 3, d("2026-03-09"))
        assert compute_streaks(days, d("2026-03-09"))[0] == 3
        assert compute_streaks(days, d("2026-03-11"))[0] == 0
        assert compute_streaks(days, d("2026-03-11"))[1] == 3

    def test_streak_gap_and_duplicates(self) -> None:
        days = [d("2026-03-01"), d("2026-03-01"), d("2026-03-02"), d("2026-03-05")]
        assert compute_streaks(days, d("2026-03-05")) == (1, 2, d("2026-03-05"))

    def test_topics_label_by_thresholds(self) -> None:
        def row(topic: str, awarded: float, n: int) -> dict[str, Any]:
            return {
                "topic": topic,
                "attempt_id": uuid.uuid4(),
                "submitted_at": datetime(2026, 3, 1, 1, tzinfo=UTC),
                "awarded": awarded,
                "available": float(n),
                "answers": n,
                "correct": int(awarded),
            }

        stats = {
            s.topic: s
            for s in compute_topics(
                [row("A", 4, 4), row("B", 1, 4), row("C", 3, 4), row("D", 1, 2)], Thresholds()
            )
        }
        assert stats["A"].status == "strong"
        assert stats["B"].status == "needs_revision"
        assert stats["C"].status == "developing"
        assert stats["D"].status == "not_enough_data"

    def test_topic_trend_needs_enough_history(self) -> None:
        rows = [
            {
                "topic": "T",
                "attempt_id": uuid.uuid4(),
                "submitted_at": datetime(2026, 3, 1 + i, tzinfo=UTC),
                "awarded": 1.0 if i >= 3 else 0.0,
                "available": 1.0,
                "answers": 1,
                "correct": 1 if i >= 3 else 0,
            }
            for i in range(6)
        ]
        t = Thresholds(min_answers=3, recent_attempts=3)
        s = compute_topics(rows, t)[0]
        assert s.recent_accuracy == 100.0 and s.previous_accuracy == 0.0
        assert s.trend == "improving"
        assert compute_topics(rows[:3], t)[0].trend is None


class TestEmptyAccount:
    async def test_everything_is_zero_or_null(
        self, client: AsyncClient, study: Harness, alice: Actor
    ) -> None:
        o = await get(client, alice, "overview")
        assert o["quiz_attempts"] == 0 and o["average_quiz_percentage"] is None
        assert o["flashcards_reviewed"] == 0 and o["time_spent_seconds"] == 0
        assert o["current_streak_days"] == 0 and o["longest_streak_days"] == 0
        assert (await get(client, alice, "quiz-performance"))["points"] == []
        assert (await get(client, alice, "subject-performance"))["items"] == []
        assert (await get(client, alice, "topic-performance"))["items"] == []
        ra = await get(client, alice, "revision-activity")
        assert ra["days"] == [] and ra["average_response_ms"] is None
        assert (await get(client, alice, "study-calendar"))["days"] == []
        s = await get(client, alice, "streaks")
        assert s["last_active_date"] is None and s["active_days_total"] == 0


class TestWithActivity:
    async def test_quiz_attempt_flows_into_every_view(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        quiz_id, t = await new_quiz(client, study, alice, db_session)
        await run_attempt(client, alice, quiz_id, t)
        today = datetime.now(UTC).date()
        o = await get(client, alice, "overview")
        assert o["quiz_attempts"] == 1 and o["quizzes_attempted"] == 1
        assert o["average_quiz_percentage"] is not None
        pts = (await get(client, alice, "quiz-performance"))["points"]
        assert len(pts) == 1 and pts[0]["quiz_id"] == quiz_id
        topics = await get(client, alice, "topic-performance")
        assert {i["topic"] for i in topics["items"]} == {"Photosynthesis", "Krebs cycle"}
        assert topics["thresholds"]["min_answers"] == 3 and "not a measure" in topics["note"]
        subj = (await get(client, alice, "subject-performance"))["items"]
        assert sum(i["quiz_attempts"] for i in subj) == 1
        cal = await get(client, alice, "study-calendar")
        assert sum(day["quiz_attempts"] for day in cal["days"]) == 1
        day = cal["days"][0]["date"]
        assert abs((d(day) - today).days) <= 1
        detail = await get(client, alice, f"study-calendar/{day}")
        assert len(detail["quizzes"]) == 1 and detail["quizzes"][0]["quiz_title"]
        assert (await get(client, alice, "streaks"))["active_days_total"] == 1

    async def test_reviews_flow_into_activity_and_streak(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        ids = await deck(client, study, alice, db_session)
        assert (await rev(client, alice, ids[0], "good")).status_code == 200
        assert (await rev(client, alice, ids[1], "again")).status_code == 200
        ra = await get(client, alice, "revision-activity")
        assert ra["total_reviews"] == 2
        assert ra["rating_distribution"] == {"again": 1, "hard": 0, "good": 1, "easy": 0}
        assert sum(day["reviews"] for day in ra["days"]) == 2
        o = await get(client, alice, "overview")
        assert o["flashcards_reviewed"] == 2 and o["distinct_cards_reviewed"] == 2
        assert (await get(client, alice, "streaks"))["active_days_total"] >= 1

    async def test_date_filter_excludes_activity(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        quiz_id, t = await new_quiz(client, study, alice, db_session)
        await run_attempt(client, alice, quiz_id, t)
        future = (datetime.now(UTC).date() + timedelta(days=3)).isoformat()
        o = await get(client, alice, f"overview?start_date={future}&end_date={future}")
        assert o["quiz_attempts"] == 0 and o["average_quiz_percentage"] is None
        assert (await get(client, alice, f"quiz-performance?start_date={future}"))["points"] == []

    async def test_unknown_subject_filter_matches_nothing(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        quiz_id, t = await new_quiz(client, study, alice, db_session)
        await run_attempt(client, alice, quiz_id, t)
        o = await get(client, alice, f"overview?subject_id={uuid.uuid4()}")
        assert o["quiz_attempts"] == 0


class TestValidationAndIsolation:
    @pytest.mark.parametrize(
        "query",
        [
            "start_date=2026-03-10&end_date=2026-03-01",
            "start_date=2020-01-01&end_date=2026-01-01",
            "start_date=not-a-date",
        ],
    )
    async def test_bad_ranges_are_rejected(
        self, client: AsyncClient, study: Harness, alice: Actor, query: str
    ) -> None:
        for path in ("revision-activity", "study-calendar"):
            resp = await _call(client, alice, "GET", f"/analytics/{path}?{query}")
            assert resp.status_code == 422, resp.text

    async def test_limit_is_capped(self, client: AsyncClient, study: Harness, alice: Actor) -> None:
        resp = await _call(client, alice, "GET", "/analytics/quiz-performance?limit=5000")
        assert resp.status_code == 422

    async def test_requires_login(self, client: AsyncClient) -> None:
        for path in ("overview", "streaks", "study-calendar", "topic-performance"):
            assert (await client.get(f"/api/v1/analytics/{path}")).status_code == 401

    async def test_other_users_see_nothing(
        self,
        client: AsyncClient,
        study: Harness,
        alice: Actor,
        bob: Actor,
        db_session: AsyncSession,
    ) -> None:
        quiz_id, t = await new_quiz(client, study, alice, db_session)
        await run_attempt(client, alice, quiz_id, t)
        ids = await deck(client, study, alice, db_session)
        await rev(client, alice, ids[0], "good")
        o = await get(client, bob, "overview")
        assert o["quiz_attempts"] == 0 and o["flashcards_reviewed"] == 0
        assert (await get(client, bob, "topic-performance"))["items"] == []
        assert (await get(client, bob, "study-calendar"))["days"] == []
        assert (await get(client, bob, "revision-activity"))["total_reviews"] == 0
        sid = str(alice.subject.id)
        assert (await get(client, bob, f"overview?subject_id={sid}"))["quiz_attempts"] == 0
        today = datetime.now(UTC).date().isoformat()
        detail = await get(client, bob, f"study-calendar/{today}")
        assert detail["quizzes"] == [] and detail["reviews"] == 0
