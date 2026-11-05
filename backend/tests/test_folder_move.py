"""Folder move (PATCH parent_folder_id) and the flat all_levels listing.

Rules under test (D-14, D-11, CLAUDE.md rules 1-3): a folder stays in its subject, is never moved
into itself or one of its descendants, its whole subtree must still fit in 3 levels, names stay
unique per parent, and other users get 404.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.subject import Subject
from app.models.workspace import Workspace
from tests.conftest import _make_session, _make_user


async def _tree_for(db: AsyncSession, email: str, ws_name: str):
    user = await _make_user(db, email=email)
    token, csrf = await _make_session(db, user)
    ws = Workspace(
        user_id=user.id, name=ws_name, workspace_type="personal_learning", is_default=False
    )
    db.add(ws)
    await db.flush()
    subject = Subject(workspace_id=ws.id, name=f"{ws_name} subject")
    db.add(subject)
    await db.flush()
    await db.commit()
    return token, csrf, ws.id, subject.id


@pytest.fixture
async def mine(db_session: AsyncSession):
    return await _tree_for(db_session, "mover@example.com", "Move WS")


@pytest.fixture
async def theirs(db_session: AsyncSession):
    return await _tree_for(db_session, "mover-other@example.com", "Their WS")


def _auth(token: str, csrf: str) -> dict:
    return {"cookies": {"aw_session": token, "csrf_token": csrf}, "headers": {"X-CSRF-Token": csrf}}


async def _mk(client, tree, name, parent=None):
    token, csrf, ws, subj = tree
    body = {"name": name}
    if parent is not None:
        body["parent_folder_id"] = parent
    resp = await client.post(
        f"/api/v1/workspaces/{ws}/subjects/{subj}/folders", json=body, **_auth(token, csrf)
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["id"]


async def _move(client, tree, folder_id, parent, *, set_flag=True, extra=None):
    token, csrf, ws, subj = tree
    body = {"parent_folder_id": parent, "parent_folder_id_set": set_flag}
    body.update(extra or {})
    return await client.patch(
        f"/api/v1/workspaces/{ws}/subjects/{subj}/folders/{folder_id}",
        json=body,
        **_auth(token, csrf),
    )


class TestMoveFolder:
    async def test_move_under_sibling(self, client: AsyncClient, mine):
        a = await _mk(client, mine, "A")
        b = await _mk(client, mine, "B")
        resp = await _move(client, mine, b, a)
        assert resp.status_code == 200
        assert resp.json()["data"]["parent_folder_id"] == a

    async def test_move_to_top_level(self, client: AsyncClient, mine):
        a = await _mk(client, mine, "A")
        b = await _mk(client, mine, "B", parent=a)
        resp = await _move(client, mine, b, None)
        assert resp.status_code == 200
        assert resp.json()["data"]["parent_folder_id"] is None

    async def test_parent_ignored_without_set_flag(self, client: AsyncClient, mine):
        a = await _mk(client, mine, "A")
        b = await _mk(client, mine, "B")
        resp = await _move(client, mine, b, a, set_flag=False, extra={"description": "kept"})
        assert resp.status_code == 200
        assert resp.json()["data"]["parent_folder_id"] is None
        assert resp.json()["data"]["description"] == "kept"

    async def test_cannot_move_into_itself(self, client: AsyncClient, mine):
        a = await _mk(client, mine, "A")
        resp = await _move(client, mine, a, a)
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "FOLDER_INVALID_MOVE"

    async def test_cannot_move_into_own_descendant(self, client: AsyncClient, mine):
        a = await _mk(client, mine, "A")
        b = await _mk(client, mine, "B", parent=a)
        c = await _mk(client, mine, "C", parent=b)
        resp = await _move(client, mine, a, c)
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "FOLDER_INVALID_MOVE"

    async def test_subtree_must_fit_in_three_levels(self, client: AsyncClient, mine):
        # Chain X > Y is 2 deep; A with child B is 2 high, so under Y it would need 4 levels.
        x = await _mk(client, mine, "X")
        y = await _mk(client, mine, "Y", parent=x)
        a = await _mk(client, mine, "A")
        await _mk(client, mine, "B", parent=a)
        too_deep = await _move(client, mine, a, y)
        assert too_deep.status_code == 422
        assert too_deep.json()["error"]["code"] == "FOLDER_DEPTH_EXCEEDED"
        # The same subtree fits under X (depth 1 + height 2 = 3).
        fits = await _move(client, mine, a, x)
        assert fits.status_code == 200

    async def test_name_conflict_at_destination(self, client: AsyncClient, mine):
        a = await _mk(client, mine, "A")
        await _mk(client, mine, "Same", parent=a)
        other = await _mk(client, mine, "same")  # case-insensitive clash (D-11)
        resp = await _move(client, mine, other, a)
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "FOLDER_NAME_CONFLICT"

    async def test_unknown_parent_is_404(self, client: AsyncClient, mine):
        a = await _mk(client, mine, "A")
        resp = await _move(client, mine, a, str(uuid.uuid4()))
        assert resp.status_code == 404

    async def test_parent_from_another_users_subject_is_404(
        self, client: AsyncClient, mine, theirs
    ):
        foreign = await _mk(client, theirs, "Foreign")
        a = await _mk(client, mine, "A")
        resp = await _move(client, mine, a, foreign)
        assert resp.status_code == 404

    async def test_other_user_cannot_move_my_folder(self, client: AsyncClient, mine, theirs):
        a = await _mk(client, mine, "A")
        b = await _mk(client, mine, "B")
        t_token, t_csrf, _, _ = theirs
        _, _, my_ws, my_subj = mine
        resp = await client.patch(
            f"/api/v1/workspaces/{my_ws}/subjects/{my_subj}/folders/{b}",
            json={"parent_folder_id": a, "parent_folder_id_set": True},
            **_auth(t_token, t_csrf),
        )
        assert resp.status_code == 404
        # And nothing moved.
        token, csrf, ws, subj = mine
        got = await client.get(
            f"/api/v1/workspaces/{ws}/subjects/{subj}/folders/{b}", **_auth(token, csrf)
        )
        assert got.json()["data"]["parent_folder_id"] is None


class TestListAllLevels:
    async def test_default_lists_only_top_level(self, client: AsyncClient, mine):
        a = await _mk(client, mine, "A")
        await _mk(client, mine, "B", parent=a)
        token, csrf, ws, subj = mine
        resp = await client.get(
            f"/api/v1/workspaces/{ws}/subjects/{subj}/folders", **_auth(token, csrf)
        )
        assert [f["name"] for f in resp.json()["data"]] == ["A"]

    async def test_all_levels_returns_every_folder_flat(self, client: AsyncClient, mine):
        a = await _mk(client, mine, "A")
        b = await _mk(client, mine, "B", parent=a)
        await _mk(client, mine, "C", parent=b)
        token, csrf, ws, subj = mine
        resp = await client.get(
            f"/api/v1/workspaces/{ws}/subjects/{subj}/folders?all_levels=true",
            **_auth(token, csrf),
        )
        assert sorted(f["name"] for f in resp.json()["data"]) == ["A", "B", "C"]

    async def test_all_levels_never_leaks_another_users_folders(
        self, client: AsyncClient, mine, theirs
    ):
        await _mk(client, theirs, "Secret")
        await _mk(client, mine, "Mine")
        token, csrf, ws, subj = mine
        resp = await client.get(
            f"/api/v1/workspaces/{ws}/subjects/{subj}/folders?all_levels=true",
            **_auth(token, csrf),
        )
        assert [f["name"] for f in resp.json()["data"]] == ["Mine"]
