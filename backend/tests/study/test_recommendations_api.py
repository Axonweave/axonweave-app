"""Phase 5 M6: rule-based revision recommendations (rules, dedupe, dismiss/complete, isolation)."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.revision import RevisionRecommendation
from tests.conftest import _TestSessionLocal
from tests.retrieval.test_search import Actor
from tests.study.conftest import Harness
from tests.study.test_quiz_assessment import new_quiz, run_attempt
from tests.study.test_revision_api import deck, set_due
from tests.test_closeout_users_config import _call


async def recs(client: AsyncClient, who: Actor) -> list[dict[str, Any]]:
    resp = await _call(client, who, "GET", "/recommendations/revision")
    assert resp.status_code == 200, resp.text
    items: list[dict[str, Any]] = resp.json()["data"]["items"]
    return items


class TestRules:
    async def test_empty_account_has_no_recommendations(
        self, client: AsyncClient, study: Harness, alice: Actor
    ) -> None:
        assert await recs(client, alice) == []
        resp = await _call(client, alice, "GET", "/recommendations/weak-topics")
        assert resp.status_code == 200 and resp.json()["data"]["items"] == []

    async def test_overdue_cards_are_high_priority_with_real_count(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        ids = await deck(client, study, alice, db_session)
        # summary creates the scheduling rows; then make two cards overdue
        await _call(client, alice, "GET", "/revision/summary")
        past = datetime.now(UTC) - timedelta(days=3)
        for card_id in ids[:2]:
            await set_due(card_id, past, state="review")
        items = await recs(client, alice)
        overdue = [i for i in items if "overdue" in i["reason"]]
        assert len(overdue) == 1
        assert overdue[0]["priority"] == "high" and overdue[0]["reason"].startswith("2 flashcards")

    async def test_weak_topic_is_reported_with_quiz_numbers(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        quiz_id, t = await new_quiz(client, study, alice, db_session)
        await run_attempt(client, alice, quiz_id, t, right=False)
        weak = (await _call(client, alice, "GET", "/recommendations/weak-topics")).json()["data"]
        assert "not a measure" in weak["note"]
        for item in weak["items"]:
            assert item["accuracy"] is not None and item["accuracy"] < 60
        items = await recs(client, alice)
        for item in items:
            assert item["recommendation_type"] in ("topic", "flashcard")
            assert item["status"] == "pending"

    async def test_repeated_calls_do_not_duplicate(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        ids = await deck(client, study, alice, db_session)
        await _call(client, alice, "GET", "/revision/summary")
        await set_due(ids[0], datetime.now(UTC) - timedelta(days=2), state="review")
        first = await recs(client, alice)
        second = await recs(client, alice)
        assert [i["id"] for i in first] == [i["id"] for i in second]
        async with _TestSessionLocal() as s:
            rows = (await s.execute(select(RevisionRecommendation))).scalars().all()
        assert len(rows) == len(first)


class TestResolve:
    async def _one(
        self, client: AsyncClient, study: Harness, alice: Actor, db: AsyncSession
    ) -> dict[str, Any]:
        ids = await deck(client, study, alice, db)
        await _call(client, alice, "GET", "/revision/summary")
        await set_due(ids[0], datetime.now(UTC) - timedelta(days=2), state="review")
        return (await recs(client, alice))[0]

    async def test_dismiss_removes_and_stays_away(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        rec = await self._one(client, study, alice, db_session)
        resp = await _call(client, alice, "POST", f"/recommendations/{rec['id']}/dismiss")
        assert resp.status_code == 200 and resp.json()["data"]["status"] == "dismissed"
        assert await recs(client, alice) == []

    async def test_complete_marks_done_and_is_idempotent(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        rec = await self._one(client, study, alice, db_session)
        first = await _call(client, alice, "POST", f"/recommendations/{rec['id']}/complete")
        again = await _call(client, alice, "POST", f"/recommendations/{rec['id']}/dismiss")
        assert first.json()["data"]["status"] == "completed"
        assert again.status_code == 200 and again.json()["data"]["status"] == "completed"

    async def test_other_users_cannot_touch_it(
        self,
        client: AsyncClient,
        study: Harness,
        alice: Actor,
        bob: Actor,
        db_session: AsyncSession,
    ) -> None:
        rec = await self._one(client, study, alice, db_session)
        for action in ("complete", "dismiss"):
            resp = await _call(client, bob, "POST", f"/recommendations/{rec['id']}/{action}")
            assert resp.status_code == 404
        assert await recs(client, bob) == []
        resp = await _call(client, alice, "POST", f"/recommendations/{uuid.uuid4()}/dismiss")
        assert resp.status_code == 404
        assert len(await recs(client, alice)) == 1

    async def test_requires_login(self, client: AsyncClient) -> None:
        assert (await client.get("/api/v1/recommendations/revision")).status_code == 401
