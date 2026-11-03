"""Tests for B4: subjects CRUD, ownership, search/filter."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workspace import Workspace
from tests.conftest import _make_session, _make_user


@pytest.fixture
async def user_with_workspace(db_session: AsyncSession):
    """Yield (user, raw_token, csrf_token, workspace_id)."""
    user = await _make_user(db_session, email="subj-user@example.com")
    raw_token, csrf_token = await _make_session(db_session, user)
    ws = Workspace(user_id=user.id, name="Test WS", workspace_type="personal_learning", is_default=False)
    db_session.add(ws)
    await db_session.flush()
    await db_session.commit()
    return user, raw_token, csrf_token, ws.id


@pytest.fixture
async def other_user_with_workspace(db_session: AsyncSession):
    """A second user + workspace for cross-user tests."""
    user = await _make_user(db_session, email="subj-other@example.com")
    raw_token, csrf_token = await _make_session(db_session, user)
    ws = Workspace(user_id=user.id, name="Other WS", workspace_type="personal_learning", is_default=False)
    db_session.add(ws)
    await db_session.flush()
    await db_session.commit()
    return user, raw_token, csrf_token, ws.id


class TestListSubjects:
    async def test_empty_list(self, client: AsyncClient, user_with_workspace):
        _, token, csrf, ws_id = user_with_workspace
        resp = await client.get(
            f"/api/v1/workspaces/{ws_id}/subjects",
            cookies={"aw_session": token},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"] == []
        assert body["total"] == 0

    async def test_requires_auth(self, client: AsyncClient, user_with_workspace):
        _, _t, _c, ws_id = user_with_workspace
        resp = await client.get(f"/api/v1/workspaces/{ws_id}/subjects")
        assert resp.status_code == 401

    async def test_wrong_workspace_returns_404(self, client: AsyncClient, user_with_workspace, other_user_with_workspace):
        """User A cannot list subjects from User B's workspace."""
        _, a_token, a_csrf, _ = user_with_workspace
        _, _t, _c, b_ws_id = other_user_with_workspace
        resp = await client.get(
            f"/api/v1/workspaces/{b_ws_id}/subjects",
            cookies={"aw_session": a_token},
            headers={"X-CSRF-Token": a_csrf},
        )
        assert resp.status_code == 404


class TestCreateSubject:
    async def test_create_success(self, client: AsyncClient, user_with_workspace):
        _, token, csrf, ws_id = user_with_workspace
        resp = await client.post(
            f"/api/v1/workspaces/{ws_id}/subjects",
            json={"name": "Mathematics", "colour": "#FF5733"},
            cookies={"aw_session": token},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["name"] == "Mathematics"
        assert body["data"]["colour"] == "#FF5733"
        assert body["data"]["workspace_id"] == str(ws_id)

    async def test_duplicate_name_409(self, client: AsyncClient, user_with_workspace):
        _, token, csrf, ws_id = user_with_workspace
        payload = {"name": "Physics"}
        await client.post(
            f"/api/v1/workspaces/{ws_id}/subjects",
            json=payload,
            cookies={"aw_session": token},
            headers={"X-CSRF-Token": csrf},
        )
        resp = await client.post(
            f"/api/v1/workspaces/{ws_id}/subjects",
            json=payload,
            cookies={"aw_session": token},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "SUBJECT_NAME_CONFLICT"

    async def test_case_insensitive_duplicate(self, client: AsyncClient, user_with_workspace):
        _, token, csrf, ws_id = user_with_workspace
        await client.post(
            f"/api/v1/workspaces/{ws_id}/subjects",
            json={"name": "Biology"},
            cookies={"aw_session": token},
            headers={"X-CSRF-Token": csrf},
        )
        resp = await client.post(
            f"/api/v1/workspaces/{ws_id}/subjects",
            json={"name": "BIOLOGY"},
            cookies={"aw_session": token},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 409

    async def test_cross_user_workspace_404(self, client: AsyncClient, user_with_workspace, other_user_with_workspace):
        _, a_token, a_csrf, _ = user_with_workspace
        _, _t, _c, b_ws_id = other_user_with_workspace
        resp = await client.post(
            f"/api/v1/workspaces/{b_ws_id}/subjects",
            json={"name": "Chemistry"},
            cookies={"aw_session": a_token},
            headers={"X-CSRF-Token": a_csrf},
        )
        assert resp.status_code == 404

    async def test_invalid_colour(self, client: AsyncClient, user_with_workspace):
        _, token, csrf, ws_id = user_with_workspace
        resp = await client.post(
            f"/api/v1/workspaces/{ws_id}/subjects",
            json={"name": "Art", "colour": "red"},
            cookies={"aw_session": token},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 422


class TestGetSubject:
    async def test_get_success(self, client: AsyncClient, user_with_workspace):
        _, token, csrf, ws_id = user_with_workspace
        create_resp = await client.post(
            f"/api/v1/workspaces/{ws_id}/subjects",
            json={"name": "History"},
            cookies={"aw_session": token},
            headers={"X-CSRF-Token": csrf},
        )
        subject_id = create_resp.json()["data"]["id"]
        resp = await client.get(
            f"/api/v1/workspaces/{ws_id}/subjects/{subject_id}",
            cookies={"aw_session": token},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == subject_id

    async def test_not_found(self, client: AsyncClient, user_with_workspace):
        _, token, csrf, ws_id = user_with_workspace
        resp = await client.get(
            f"/api/v1/workspaces/{ws_id}/subjects/00000000-0000-0000-0000-000000000000",
            cookies={"aw_session": token},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 404

    async def test_cross_user_returns_404(self, client: AsyncClient, user_with_workspace, other_user_with_workspace):
        _, a_token, a_csrf, a_ws_id = user_with_workspace
        _, b_token, b_csrf, b_ws_id = other_user_with_workspace
        # B creates a subject
        create_resp = await client.post(
            f"/api/v1/workspaces/{b_ws_id}/subjects",
            json={"name": "Art"},
            cookies={"aw_session": b_token},
            headers={"X-CSRF-Token": b_csrf},
        )
        subject_id = create_resp.json()["data"]["id"]
        # A tries to access it via A's workspace (wrong workspace_id)
        resp = await client.get(
            f"/api/v1/workspaces/{a_ws_id}/subjects/{subject_id}",
            cookies={"aw_session": a_token},
            headers={"X-CSRF-Token": a_csrf},
        )
        assert resp.status_code == 404


class TestUpdateSubject:
    async def test_update_name(self, client: AsyncClient, user_with_workspace):
        _, token, csrf, ws_id = user_with_workspace
        create_resp = await client.post(
            f"/api/v1/workspaces/{ws_id}/subjects",
            json={"name": "Old Name"},
            cookies={"aw_session": token},
            headers={"X-CSRF-Token": csrf},
        )
        subject_id = create_resp.json()["data"]["id"]
        resp = await client.patch(
            f"/api/v1/workspaces/{ws_id}/subjects/{subject_id}",
            json={"name": "New Name"},
            cookies={"aw_session": token},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "New Name"

    async def test_rename_conflict(self, client: AsyncClient, user_with_workspace):
        _, token, csrf, ws_id = user_with_workspace
        await client.post(
            f"/api/v1/workspaces/{ws_id}/subjects",
            json={"name": "Alpha"},
            cookies={"aw_session": token},
            headers={"X-CSRF-Token": csrf},
        )
        create_resp = await client.post(
            f"/api/v1/workspaces/{ws_id}/subjects",
            json={"name": "Beta"},
            cookies={"aw_session": token},
            headers={"X-CSRF-Token": csrf},
        )
        subject_id = create_resp.json()["data"]["id"]
        resp = await client.patch(
            f"/api/v1/workspaces/{ws_id}/subjects/{subject_id}",
            json={"name": "Alpha"},
            cookies={"aw_session": token},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 409


class TestArchiveRestoreSubject:
    async def test_archive_and_restore(self, client: AsyncClient, user_with_workspace):
        _, token, csrf, ws_id = user_with_workspace
        create_resp = await client.post(
            f"/api/v1/workspaces/{ws_id}/subjects",
            json={"name": "Geography"},
            cookies={"aw_session": token},
            headers={"X-CSRF-Token": csrf},
        )
        subject_id = create_resp.json()["data"]["id"]

        # Archive
        archive_resp = await client.post(
            f"/api/v1/workspaces/{ws_id}/subjects/{subject_id}/archive",
            cookies={"aw_session": token},
            headers={"X-CSRF-Token": csrf},
        )
        assert archive_resp.status_code == 200
        assert archive_resp.json()["data"]["archived_at"] is not None

        # Restore
        restore_resp = await client.post(
            f"/api/v1/workspaces/{ws_id}/subjects/{subject_id}/restore",
            cookies={"aw_session": token},
            headers={"X-CSRF-Token": csrf},
        )
        assert restore_resp.status_code == 200
        assert restore_resp.json()["data"]["archived_at"] is None

    async def test_double_archive_409(self, client: AsyncClient, user_with_workspace):
        _, token, csrf, ws_id = user_with_workspace
        create_resp = await client.post(
            f"/api/v1/workspaces/{ws_id}/subjects",
            json={"name": "Economics"},
            cookies={"aw_session": token},
            headers={"X-CSRF-Token": csrf},
        )
        subject_id = create_resp.json()["data"]["id"]
        await client.post(
            f"/api/v1/workspaces/{ws_id}/subjects/{subject_id}/archive",
            cookies={"aw_session": token},
            headers={"X-CSRF-Token": csrf},
        )
        resp = await client.post(
            f"/api/v1/workspaces/{ws_id}/subjects/{subject_id}/archive",
            cookies={"aw_session": token},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 409

    async def test_archived_not_in_default_list(self, client: AsyncClient, user_with_workspace):
        _, token, csrf, ws_id = user_with_workspace
        create_resp = await client.post(
            f"/api/v1/workspaces/{ws_id}/subjects",
            json={"name": "Music"},
            cookies={"aw_session": token},
            headers={"X-CSRF-Token": csrf},
        )
        subject_id = create_resp.json()["data"]["id"]
        await client.post(
            f"/api/v1/workspaces/{ws_id}/subjects/{subject_id}/archive",
            cookies={"aw_session": token},
            headers={"X-CSRF-Token": csrf},
        )
        list_resp = await client.get(
            f"/api/v1/workspaces/{ws_id}/subjects",
            cookies={"aw_session": token},
            headers={"X-CSRF-Token": csrf},
        )
        ids = [s["id"] for s in list_resp.json()["data"]]
        assert subject_id not in ids

    async def test_archived_in_include_archived_list(self, client: AsyncClient, user_with_workspace):
        _, token, csrf, ws_id = user_with_workspace
        create_resp = await client.post(
            f"/api/v1/workspaces/{ws_id}/subjects",
            json={"name": "Drama"},
            cookies={"aw_session": token},
            headers={"X-CSRF-Token": csrf},
        )
        subject_id = create_resp.json()["data"]["id"]
        await client.post(
            f"/api/v1/workspaces/{ws_id}/subjects/{subject_id}/archive",
            cookies={"aw_session": token},
            headers={"X-CSRF-Token": csrf},
        )
        list_resp = await client.get(
            f"/api/v1/workspaces/{ws_id}/subjects?include_archived=true",
            cookies={"aw_session": token},
            headers={"X-CSRF-Token": csrf},
        )
        ids = [s["id"] for s in list_resp.json()["data"]]
        assert subject_id in ids


class TestDeleteSubject:
    async def test_delete_success(self, client: AsyncClient, user_with_workspace):
        _, token, csrf, ws_id = user_with_workspace
        create_resp = await client.post(
            f"/api/v1/workspaces/{ws_id}/subjects",
            json={"name": "To Delete"},
            cookies={"aw_session": token},
            headers={"X-CSRF-Token": csrf},
        )
        subject_id = create_resp.json()["data"]["id"]
        resp = await client.delete(
            f"/api/v1/workspaces/{ws_id}/subjects/{subject_id}",
            cookies={"aw_session": token},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 204

    async def test_delete_cross_user_404(self, client: AsyncClient, user_with_workspace, other_user_with_workspace):
        _, a_token, a_csrf, a_ws_id = user_with_workspace
        _, b_token, b_csrf, b_ws_id = other_user_with_workspace
        create_resp = await client.post(
            f"/api/v1/workspaces/{b_ws_id}/subjects",
            json={"name": "Steal Me"},
            cookies={"aw_session": b_token},
            headers={"X-CSRF-Token": b_csrf},
        )
        subject_id = create_resp.json()["data"]["id"]
        resp = await client.delete(
            f"/api/v1/workspaces/{a_ws_id}/subjects/{subject_id}",
            cookies={"aw_session": a_token},
            headers={"X-CSRF-Token": a_csrf},
        )
        assert resp.status_code == 404


class TestSearchAndFilter:
    async def test_search_by_name(self, client: AsyncClient, user_with_workspace):
        _, token, csrf, ws_id = user_with_workspace
        for name in ["Calculus", "Statistics", "Linear Algebra"]:
            await client.post(
                f"/api/v1/workspaces/{ws_id}/subjects",
                json={"name": name},
                cookies={"aw_session": token},
                headers={"X-CSRF-Token": csrf},
            )
        resp = await client.get(
            f"/api/v1/workspaces/{ws_id}/subjects?q=calc",
            cookies={"aw_session": token},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 200
        names = [s["name"] for s in resp.json()["data"]]
        assert "Calculus" in names
        assert "Statistics" not in names
