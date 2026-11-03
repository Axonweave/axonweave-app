"""Tests for B6: dashboard stats and activity — real counts, no fake data (D-30)."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workspace import Workspace
from tests.conftest import _make_session, _make_user


@pytest.fixture
async def dashboard_user(db_session: AsyncSession):
    user = await _make_user(db_session, email="dash@example.com")
    raw_token, csrf_token = await _make_session(db_session, user)
    await db_session.commit()
    return user, raw_token, csrf_token


class TestDashboardStats:
    async def test_stats_requires_auth(self, client: AsyncClient):
        resp = await client.get("/api/v1/dashboard/stats")
        assert resp.status_code == 401

    async def test_stats_returns_real_counts(self, client: AsyncClient, dashboard_user):
        _, token, csrf = dashboard_user
        resp = await client.get(
            "/api/v1/dashboard/stats",
            cookies={"aw_session": token},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        data = body["data"]
        # Fixture creates a "Personal" workspace on register
        assert data["workspace_count"] >= 1
        assert "subject_count" in data
        assert "folder_count" in data
        assert "chapter_count" in data
        assert "chapter_status" in data
        cs = data["chapter_status"]
        assert "not_started" in cs
        assert "in_progress" in cs
        assert "completed" in cs

    async def test_stats_zero_state(self, client: AsyncClient, dashboard_user):
        """New user with no subjects/chapters returns zero for those counts."""
        _, token, csrf = dashboard_user
        resp = await client.get(
            "/api/v1/dashboard/stats",
            cookies={"aw_session": token},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["subject_count"] == 0
        assert data["folder_count"] == 0
        assert data["chapter_count"] == 0
        assert data["chapter_status"]["not_started"] == 0
        assert data["chapter_status"]["in_progress"] == 0
        assert data["chapter_status"]["completed"] == 0

    async def test_stats_scoped_to_user(self, client: AsyncClient, db_session: AsyncSession):
        """Two users see only their own counts."""
        user_a = await _make_user(db_session, email="dash-a@example.com")
        token_a, csrf_a = await _make_session(db_session, user_a)
        user_b = await _make_user(db_session, email="dash-b@example.com")
        token_b, csrf_b = await _make_session(db_session, user_b)
        # Give B an extra workspace
        db_session.add(Workspace(user_id=user_b.id, name="B Extra", workspace_type="personal_learning", is_default=False))
        await db_session.commit()

        resp_a = await client.get(
            "/api/v1/dashboard/stats",
            cookies={"aw_session": token_a},
            headers={"X-CSRF-Token": csrf_a},
        )
        resp_b = await client.get(
            "/api/v1/dashboard/stats",
            cookies={"aw_session": token_b},
            headers={"X-CSRF-Token": csrf_b},
        )
        assert resp_a.status_code == 200
        assert resp_b.status_code == 200
        a_ws = resp_a.json()["data"]["workspace_count"]
        b_ws = resp_b.json()["data"]["workspace_count"]
        # B has one extra workspace
        assert b_ws == a_ws + 1


class TestDashboardActivity:
    async def test_activity_requires_auth(self, client: AsyncClient):
        resp = await client.get("/api/v1/dashboard/activity")
        assert resp.status_code == 401

    async def test_activity_empty_for_new_user(self, client: AsyncClient, dashboard_user):
        _, token, csrf = dashboard_user
        resp = await client.get(
            "/api/v1/dashboard/activity",
            cookies={"aw_session": token},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert isinstance(body["data"], list)
        assert "total" in body

    async def test_activity_pagination(self, client: AsyncClient, dashboard_user):
        _, token, csrf = dashboard_user
        resp = await client.get(
            "/api/v1/dashboard/activity?limit=5&offset=0",
            cookies={"aw_session": token},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 200

    async def test_activity_limit_cap(self, client: AsyncClient, dashboard_user):
        _, token, csrf = dashboard_user
        resp = await client.get(
            "/api/v1/dashboard/activity?limit=999",
            cookies={"aw_session": token},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 422
