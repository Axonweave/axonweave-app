"""Tests for B5: folders and chapters CRUD, depth limit, cascade delete, reorder."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.subject import Subject
from app.models.workspace import Workspace
from tests.conftest import _make_session, _make_user


@pytest.fixture
async def full_tree(db_session: AsyncSession):
    """Yield (user, token, csrf, workspace_id, subject_id) for a user with workspace + subject."""
    user = await _make_user(db_session, email="tree-user@example.com")
    raw_token, csrf_token = await _make_session(db_session, user)
    ws = Workspace(
        user_id=user.id, name="FC WS", workspace_type="personal_learning", is_default=False
    )
    db_session.add(ws)
    await db_session.flush()
    subj = Subject(workspace_id=ws.id, name="FC Subject")
    db_session.add(subj)
    await db_session.flush()
    await db_session.commit()
    return user, raw_token, csrf_token, ws.id, subj.id


@pytest.fixture
async def other_tree(db_session: AsyncSession):
    user = await _make_user(db_session, email="tree-other@example.com")
    raw_token, csrf_token = await _make_session(db_session, user)
    ws = Workspace(
        user_id=user.id, name="Other WS", workspace_type="personal_learning", is_default=False
    )
    db_session.add(ws)
    await db_session.flush()
    subj = Subject(workspace_id=ws.id, name="Other Subject")
    db_session.add(subj)
    await db_session.flush()
    await db_session.commit()
    return user, raw_token, csrf_token, ws.id, subj.id


# ── Folder tests ──────────────────────────────────────────────────────────────


class TestFolderCRUD:
    async def test_create_root_folder(self, client: AsyncClient, full_tree):
        _, token, csrf, ws_id, subj_id = full_tree
        resp = await client.post(
            f"/api/v1/workspaces/{ws_id}/subjects/{subj_id}/folders",
            json={"name": "Chapter 1"},
            cookies={"aw_session": token, "csrf_token": csrf},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["name"] == "Chapter 1"
        assert data["parent_folder_id"] is None
        assert data["subject_id"] == str(subj_id)

    async def test_list_folders(self, client: AsyncClient, full_tree):
        _, token, csrf, ws_id, subj_id = full_tree
        await client.post(
            f"/api/v1/workspaces/{ws_id}/subjects/{subj_id}/folders",
            json={"name": "Root Folder"},
            cookies={"aw_session": token, "csrf_token": csrf},
            headers={"X-CSRF-Token": csrf},
        )
        resp = await client.get(
            f"/api/v1/workspaces/{ws_id}/subjects/{subj_id}/folders",
            cookies={"aw_session": token, "csrf_token": csrf},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 200
        assert len(resp.json()["data"]) >= 1

    async def test_get_folder(self, client: AsyncClient, full_tree):
        _, token, csrf, ws_id, subj_id = full_tree
        create_resp = await client.post(
            f"/api/v1/workspaces/{ws_id}/subjects/{subj_id}/folders",
            json={"name": "Get Me"},
            cookies={"aw_session": token, "csrf_token": csrf},
            headers={"X-CSRF-Token": csrf},
        )
        folder_id = create_resp.json()["data"]["id"]
        resp = await client.get(
            f"/api/v1/workspaces/{ws_id}/subjects/{subj_id}/folders/{folder_id}",
            cookies={"aw_session": token, "csrf_token": csrf},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == folder_id

    async def test_update_folder(self, client: AsyncClient, full_tree):
        _, token, csrf, ws_id, subj_id = full_tree
        create_resp = await client.post(
            f"/api/v1/workspaces/{ws_id}/subjects/{subj_id}/folders",
            json={"name": "Old Name"},
            cookies={"aw_session": token, "csrf_token": csrf},
            headers={"X-CSRF-Token": csrf},
        )
        folder_id = create_resp.json()["data"]["id"]
        resp = await client.patch(
            f"/api/v1/workspaces/{ws_id}/subjects/{subj_id}/folders/{folder_id}",
            json={"name": "New Name"},
            cookies={"aw_session": token, "csrf_token": csrf},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "New Name"

    async def test_delete_empty_folder(self, client: AsyncClient, full_tree):
        _, token, csrf, ws_id, subj_id = full_tree
        create_resp = await client.post(
            f"/api/v1/workspaces/{ws_id}/subjects/{subj_id}/folders",
            json={"name": "Delete Me"},
            cookies={"aw_session": token, "csrf_token": csrf},
            headers={"X-CSRF-Token": csrf},
        )
        folder_id = create_resp.json()["data"]["id"]
        resp = await client.delete(
            f"/api/v1/workspaces/{ws_id}/subjects/{subj_id}/folders/{folder_id}",
            cookies={"aw_session": token, "csrf_token": csrf},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 204

    async def test_cross_user_folder_404(self, client: AsyncClient, full_tree, other_tree):
        _, a_token, a_csrf, a_ws_id, a_subj_id = full_tree
        _, b_token, b_csrf, b_ws_id, b_subj_id = other_tree
        # B creates a folder
        b_resp = await client.post(
            f"/api/v1/workspaces/{b_ws_id}/subjects/{b_subj_id}/folders",
            json={"name": "B Folder"},
            cookies={"aw_session": b_token, "csrf_token": b_csrf},
            headers={"X-CSRF-Token": b_csrf},
        )
        folder_id = b_resp.json()["data"]["id"]
        # A tries to access via A's subject (wrong subject_id)
        resp = await client.get(
            f"/api/v1/workspaces/{a_ws_id}/subjects/{a_subj_id}/folders/{folder_id}",
            cookies={"aw_session": a_token, "csrf_token": a_csrf},
            headers={"X-CSRF-Token": a_csrf},
        )
        assert resp.status_code == 404


class TestFolderDepthLimit:
    async def test_create_nested_folder_level2(self, client: AsyncClient, full_tree):
        _, token, csrf, ws_id, subj_id = full_tree
        parent = await client.post(
            f"/api/v1/workspaces/{ws_id}/subjects/{subj_id}/folders",
            json={"name": "Level 1 Depth"},
            cookies={"aw_session": token, "csrf_token": csrf},
            headers={"X-CSRF-Token": csrf},
        )
        parent_id = parent.json()["data"]["id"]
        resp = await client.post(
            f"/api/v1/workspaces/{ws_id}/subjects/{subj_id}/folders",
            json={"name": "Level 2", "parent_folder_id": parent_id},
            cookies={"aw_session": token, "csrf_token": csrf},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 201

    async def test_create_nested_folder_level3(self, client: AsyncClient, full_tree):
        _, token, csrf, ws_id, subj_id = full_tree
        l1 = (
            await client.post(
                f"/api/v1/workspaces/{ws_id}/subjects/{subj_id}/folders",
                json={"name": "L1"},
                cookies={"aw_session": token, "csrf_token": csrf},
                headers={"X-CSRF-Token": csrf},
            )
        ).json()["data"]["id"]
        l2 = (
            await client.post(
                f"/api/v1/workspaces/{ws_id}/subjects/{subj_id}/folders",
                json={"name": "L2", "parent_folder_id": l1},
                cookies={"aw_session": token, "csrf_token": csrf},
                headers={"X-CSRF-Token": csrf},
            )
        ).json()["data"]["id"]
        resp = await client.post(
            f"/api/v1/workspaces/{ws_id}/subjects/{subj_id}/folders",
            json={"name": "L3", "parent_folder_id": l2},
            cookies={"aw_session": token, "csrf_token": csrf},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 201

    async def test_create_beyond_max_depth_rejected(self, client: AsyncClient, full_tree):
        _, token, csrf, ws_id, subj_id = full_tree
        l1 = (
            await client.post(
                f"/api/v1/workspaces/{ws_id}/subjects/{subj_id}/folders",
                json={"name": "D1"},
                cookies={"aw_session": token, "csrf_token": csrf},
                headers={"X-CSRF-Token": csrf},
            )
        ).json()["data"]["id"]
        l2 = (
            await client.post(
                f"/api/v1/workspaces/{ws_id}/subjects/{subj_id}/folders",
                json={"name": "D2", "parent_folder_id": l1},
                cookies={"aw_session": token, "csrf_token": csrf},
                headers={"X-CSRF-Token": csrf},
            )
        ).json()["data"]["id"]
        l3 = (
            await client.post(
                f"/api/v1/workspaces/{ws_id}/subjects/{subj_id}/folders",
                json={"name": "D3", "parent_folder_id": l2},
                cookies={"aw_session": token, "csrf_token": csrf},
                headers={"X-CSRF-Token": csrf},
            )
        ).json()["data"]["id"]
        resp = await client.post(
            f"/api/v1/workspaces/{ws_id}/subjects/{subj_id}/folders",
            json={"name": "D4 too deep", "parent_folder_id": l3},
            cookies={"aw_session": token, "csrf_token": csrf},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "FOLDER_DEPTH_EXCEEDED"


class TestFolderCascadeDelete:
    async def test_delete_non_empty_without_cascade_409(self, client: AsyncClient, full_tree):
        _, token, csrf, ws_id, subj_id = full_tree
        parent = (
            await client.post(
                f"/api/v1/workspaces/{ws_id}/subjects/{subj_id}/folders",
                json={"name": "Parent Cascade"},
                cookies={"aw_session": token, "csrf_token": csrf},
                headers={"X-CSRF-Token": csrf},
            )
        ).json()["data"]["id"]
        await client.post(
            f"/api/v1/workspaces/{ws_id}/subjects/{subj_id}/folders",
            json={"name": "Child", "parent_folder_id": parent},
            cookies={"aw_session": token, "csrf_token": csrf},
            headers={"X-CSRF-Token": csrf},
        )
        resp = await client.delete(
            f"/api/v1/workspaces/{ws_id}/subjects/{subj_id}/folders/{parent}",
            cookies={"aw_session": token, "csrf_token": csrf},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "FOLDER_NOT_EMPTY"

    async def test_delete_non_empty_with_cascade(self, client: AsyncClient, full_tree):
        _, token, csrf, ws_id, subj_id = full_tree
        parent = (
            await client.post(
                f"/api/v1/workspaces/{ws_id}/subjects/{subj_id}/folders",
                json={"name": "Cascade Delete"},
                cookies={"aw_session": token, "csrf_token": csrf},
                headers={"X-CSRF-Token": csrf},
            )
        ).json()["data"]["id"]
        await client.post(
            f"/api/v1/workspaces/{ws_id}/subjects/{subj_id}/folders",
            json={"name": "Child to cascade", "parent_folder_id": parent},
            cookies={"aw_session": token, "csrf_token": csrf},
            headers={"X-CSRF-Token": csrf},
        )
        resp = await client.delete(
            f"/api/v1/workspaces/{ws_id}/subjects/{subj_id}/folders/{parent}?cascade=true",
            cookies={"aw_session": token, "csrf_token": csrf},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 204


class TestFolderArchive:
    async def test_archive_and_restore(self, client: AsyncClient, full_tree):
        _, token, csrf, ws_id, subj_id = full_tree
        folder_id = (
            await client.post(
                f"/api/v1/workspaces/{ws_id}/subjects/{subj_id}/folders",
                json={"name": "Archive Me"},
                cookies={"aw_session": token, "csrf_token": csrf},
                headers={"X-CSRF-Token": csrf},
            )
        ).json()["data"]["id"]
        archive_resp = await client.post(
            f"/api/v1/workspaces/{ws_id}/subjects/{subj_id}/folders/{folder_id}/archive",
            cookies={"aw_session": token, "csrf_token": csrf},
            headers={"X-CSRF-Token": csrf},
        )
        assert archive_resp.status_code == 200
        assert archive_resp.json()["data"]["archived_at"] is not None

        restore_resp = await client.post(
            f"/api/v1/workspaces/{ws_id}/subjects/{subj_id}/folders/{folder_id}/restore",
            cookies={"aw_session": token, "csrf_token": csrf},
            headers={"X-CSRF-Token": csrf},
        )
        assert restore_resp.status_code == 200
        assert restore_resp.json()["data"]["archived_at"] is None


# ── Chapter tests ─────────────────────────────────────────────────────────────


class TestChapterCRUD:
    async def test_create_chapter(self, client: AsyncClient, full_tree):
        _, token, csrf, ws_id, subj_id = full_tree
        resp = await client.post(
            f"/api/v1/workspaces/{ws_id}/subjects/{subj_id}/chapters",
            json={"title": "Introduction"},
            cookies={"aw_session": token, "csrf_token": csrf},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["title"] == "Introduction"
        assert data["status"] == "not_started"
        assert data["folder_id"] is None

    async def test_create_chapter_in_folder(self, client: AsyncClient, full_tree):
        _, token, csrf, ws_id, subj_id = full_tree
        folder_id = (
            await client.post(
                f"/api/v1/workspaces/{ws_id}/subjects/{subj_id}/folders",
                json={"name": "Chap Folder"},
                cookies={"aw_session": token, "csrf_token": csrf},
                headers={"X-CSRF-Token": csrf},
            )
        ).json()["data"]["id"]
        resp = await client.post(
            f"/api/v1/workspaces/{ws_id}/subjects/{subj_id}/chapters",
            json={"title": "Ch in folder", "folder_id": folder_id},
            cookies={"aw_session": token, "csrf_token": csrf},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 201
        assert resp.json()["data"]["folder_id"] == folder_id

    async def test_list_chapters(self, client: AsyncClient, full_tree):
        _, token, csrf, ws_id, subj_id = full_tree
        await client.post(
            f"/api/v1/workspaces/{ws_id}/subjects/{subj_id}/chapters",
            json={"title": "List Chapter"},
            cookies={"aw_session": token, "csrf_token": csrf},
            headers={"X-CSRF-Token": csrf},
        )
        resp = await client.get(
            f"/api/v1/workspaces/{ws_id}/subjects/{subj_id}/chapters",
            cookies={"aw_session": token, "csrf_token": csrf},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    async def test_update_chapter_status(self, client: AsyncClient, full_tree):
        _, token, csrf, ws_id, subj_id = full_tree
        chapter_id = (
            await client.post(
                f"/api/v1/workspaces/{ws_id}/subjects/{subj_id}/chapters",
                json={"title": "Update Me"},
                cookies={"aw_session": token, "csrf_token": csrf},
                headers={"X-CSRF-Token": csrf},
            )
        ).json()["data"]["id"]
        resp = await client.patch(
            f"/api/v1/workspaces/{ws_id}/subjects/{subj_id}/chapters/{chapter_id}",
            json={"status": "completed"},
            cookies={"aw_session": token, "csrf_token": csrf},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "completed"

    async def test_delete_chapter(self, client: AsyncClient, full_tree):
        _, token, csrf, ws_id, subj_id = full_tree
        chapter_id = (
            await client.post(
                f"/api/v1/workspaces/{ws_id}/subjects/{subj_id}/chapters",
                json={"title": "Delete Me"},
                cookies={"aw_session": token, "csrf_token": csrf},
                headers={"X-CSRF-Token": csrf},
            )
        ).json()["data"]["id"]
        resp = await client.delete(
            f"/api/v1/workspaces/{ws_id}/subjects/{subj_id}/chapters/{chapter_id}",
            cookies={"aw_session": token, "csrf_token": csrf},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 204

    async def test_cross_user_chapter_404(self, client: AsyncClient, full_tree, other_tree):
        _, a_token, a_csrf, a_ws_id, a_subj_id = full_tree
        _, b_token, b_csrf, b_ws_id, b_subj_id = other_tree
        b_chapter_id = (
            await client.post(
                f"/api/v1/workspaces/{b_ws_id}/subjects/{b_subj_id}/chapters",
                json={"title": "B's Chapter"},
                cookies={"aw_session": b_token, "csrf_token": b_csrf},
                headers={"X-CSRF-Token": b_csrf},
            )
        ).json()["data"]["id"]
        resp = await client.get(
            f"/api/v1/workspaces/{a_ws_id}/subjects/{a_subj_id}/chapters/{b_chapter_id}",
            cookies={"aw_session": a_token, "csrf_token": a_csrf},
            headers={"X-CSRF-Token": a_csrf},
        )
        assert resp.status_code == 404

    async def test_requires_auth(self, client: AsyncClient, full_tree):
        _, _t, _c, ws_id, subj_id = full_tree
        resp = await client.get(f"/api/v1/workspaces/{ws_id}/subjects/{subj_id}/chapters")
        assert resp.status_code == 401


class TestChapterReorder:
    async def test_reorder_chapters(self, client: AsyncClient, full_tree):
        _, token, csrf, ws_id, subj_id = full_tree
        ids = []
        for i, title in enumerate(["Alpha", "Beta", "Gamma"]):
            cid = (
                await client.post(
                    f"/api/v1/workspaces/{ws_id}/subjects/{subj_id}/chapters",
                    json={"title": title, "display_order": i},
                    cookies={"aw_session": token, "csrf_token": csrf},
                    headers={"X-CSRF-Token": csrf},
                )
            ).json()["data"]["id"]
            ids.append(cid)

        # Reorder in reverse
        resp = await client.post(
            f"/api/v1/workspaces/{ws_id}/subjects/{subj_id}/chapters/reorder",
            json={"chapter_ids": list(reversed(ids))},
            cookies={"aw_session": token, "csrf_token": csrf},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True


class TestChapterArchive:
    async def test_archive_and_restore(self, client: AsyncClient, full_tree):
        _, token, csrf, ws_id, subj_id = full_tree
        chapter_id = (
            await client.post(
                f"/api/v1/workspaces/{ws_id}/subjects/{subj_id}/chapters",
                json={"title": "Archive Chapter"},
                cookies={"aw_session": token, "csrf_token": csrf},
                headers={"X-CSRF-Token": csrf},
            )
        ).json()["data"]["id"]

        archive_resp = await client.post(
            f"/api/v1/workspaces/{ws_id}/subjects/{subj_id}/chapters/{chapter_id}/archive",
            cookies={"aw_session": token, "csrf_token": csrf},
            headers={"X-CSRF-Token": csrf},
        )
        assert archive_resp.status_code == 200
        assert archive_resp.json()["data"]["archived_at"] is not None

        restore_resp = await client.post(
            f"/api/v1/workspaces/{ws_id}/subjects/{subj_id}/chapters/{chapter_id}/restore",
            cookies={"aw_session": token, "csrf_token": csrf},
            headers={"X-CSRF-Token": csrf},
        )
        assert restore_resp.status_code == 200
        assert restore_resp.json()["data"]["archived_at"] is None

    async def test_archived_not_in_default_list(self, client: AsyncClient, full_tree):
        _, token, csrf, ws_id, subj_id = full_tree
        chapter_id = (
            await client.post(
                f"/api/v1/workspaces/{ws_id}/subjects/{subj_id}/chapters",
                json={"title": "Hide Me"},
                cookies={"aw_session": token, "csrf_token": csrf},
                headers={"X-CSRF-Token": csrf},
            )
        ).json()["data"]["id"]
        await client.post(
            f"/api/v1/workspaces/{ws_id}/subjects/{subj_id}/chapters/{chapter_id}/archive",
            cookies={"aw_session": token, "csrf_token": csrf},
            headers={"X-CSRF-Token": csrf},
        )
        list_resp = await client.get(
            f"/api/v1/workspaces/{ws_id}/subjects/{subj_id}/chapters",
            cookies={"aw_session": token, "csrf_token": csrf},
            headers={"X-CSRF-Token": csrf},
        )
        ids = [c["id"] for c in list_resp.json()["data"]]
        assert chapter_id not in ids
