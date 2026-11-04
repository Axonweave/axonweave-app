"""Tests for dashboard pages: activity recording, workspace overview, recent subjects, archived.

Every endpoint has an unauthenticated test and a cross-user test (user B never sees user A's rows).
"""

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chapter import Chapter
from app.models.folder import Folder
from app.models.subject import Subject
from app.models.workspace import Workspace
from tests.conftest import _make_session, _make_user


class Actor:
    def __init__(self, user, token: str, csrf: str) -> None:
        self.user = user
        self.cookies = {"aw_session": token, "csrf_token": csrf}
        self.headers = {"X-CSRF-Token": csrf}


async def _actor(db: AsyncSession, email: str) -> Actor:
    user = await _make_user(db, email=email)
    token, csrf = await _make_session(db, user)
    await db.commit()
    return Actor(user, token, csrf)


@pytest.fixture
async def alice(db_session: AsyncSession) -> Actor:
    return await _actor(db_session, "alice-pages@example.com")


@pytest.fixture
async def bob(db_session: AsyncSession) -> Actor:
    return await _actor(db_session, "bob-pages@example.com")


async def _get(client: AsyncClient, who: Actor, url: str):
    return await client.get(f"/api/v1{url}", cookies=who.cookies, headers=who.headers)


async def _seed_tree(db: AsyncSession, who: Actor, *, archived: bool = False):
    """One workspace with a subject, folder and chapter, optionally all archived."""
    now = datetime.now(UTC) if archived else None
    ws = Workspace(
        user_id=who.user.id,
        name=f"WS of {who.user.email}",
        workspace_type="personal_learning",
        is_default=False,
        archived_at=now,
    )
    db.add(ws)
    await db.flush()
    subject = Subject(workspace_id=ws.id, name="Maths", archived_at=now)
    db.add(subject)
    await db.flush()
    folder = Folder(subject_id=subject.id, name="Algebra", archived_at=now)
    chapter = Chapter(subject_id=subject.id, title="Limits", archived_at=now)
    db.add_all([folder, chapter])
    await db.commit()
    return ws, subject, folder, chapter


class TestActivityRecording:
    async def test_actions_are_recorded_and_listed(self, client: AsyncClient, alice: Actor):
        base = {"cookies": alice.cookies, "headers": alice.headers}
        ws = (await client.post("/api/v1/workspaces", json={"name": "Uni"}, **base)).json()["data"]
        sub = (
            await client.post(
                f"/api/v1/workspaces/{ws['id']}/subjects", json={"name": "Physics"}, **base
            )
        ).json()["data"]
        folder = (
            await client.post(
                f"/api/v1/workspaces/{ws['id']}/subjects/{sub['id']}/folders",
                json={"name": "Optics"},
                **base,
            )
        ).json()["data"]
        chapter = (
            await client.post(
                f"/api/v1/workspaces/{ws['id']}/subjects/{sub['id']}/chapters",
                json={"title": "Lenses"},
                **base,
            )
        ).json()["data"]
        resp = await client.post(
            f"/api/v1/workspaces/{ws['id']}/subjects/{sub['id']}/chapters/{chapter['id']}/archive",
            **base,
        )
        assert resp.status_code == 200

        body = (await _get(client, alice, "/dashboard/activity")).json()
        pairs = [(i["action"], i["entity_type"], i["entity_name"]) for i in body["data"]]
        assert ("created", "workspace", "Uni") in pairs
        assert ("created", "subject", "Physics") in pairs
        assert ("created", "folder", "Optics") in pairs
        assert ("created", "chapter", "Lenses") in pairs
        assert ("archived", "chapter", "Lenses") in pairs
        by_key = {(i["action"], i["entity_type"]): i for i in body["data"]}
        assert by_key[("archived", "chapter")]["entity_status"] == "archived"
        assert by_key[("created", "folder")]["entity_status"] == "active"
        assert folder["id"] == by_key[("created", "folder")]["entity_id"]

    async def test_deleted_entity_is_marked_deleted(self, client: AsyncClient, alice: Actor):
        base = {"cookies": alice.cookies, "headers": alice.headers}
        ws = (await client.post("/api/v1/workspaces", json={"name": "Temp"}, **base)).json()["data"]
        resp = await client.delete(f"/api/v1/workspaces/{ws['id']}", **base)
        assert resp.status_code == 200
        items = (await _get(client, alice, "/dashboard/activity")).json()["data"]
        deleted = [i for i in items if i["action"] == "deleted"]
        assert deleted and deleted[0]["entity_status"] == "deleted"
        created = [i for i in items if i["action"] == "created"]
        assert created and created[0]["entity_status"] == "deleted"

    async def test_activity_not_visible_to_other_user(
        self, client: AsyncClient, alice: Actor, bob: Actor
    ):
        await client.post(
            "/api/v1/workspaces",
            json={"name": "Secret"},
            cookies=alice.cookies,
            headers=alice.headers,
        )
        body = (await _get(client, bob, "/dashboard/activity")).json()
        assert body["total"] == 0
        assert body["data"] == []


class TestWorkspaceOverview:
    async def test_requires_auth(self, client: AsyncClient):
        assert (await client.get("/api/v1/dashboard/workspaces")).status_code == 401

    async def test_counts_non_archived_subjects(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor
    ):
        ws, _, _, _ = await _seed_tree(db_session, alice)
        db_session.add(
            Subject(workspace_id=ws.id, name="Archived one", archived_at=datetime.now(UTC))
        )
        await db_session.commit()
        body = (await _get(client, alice, "/dashboard/workspaces")).json()
        by_name = {w["name"]: w for w in body["data"]}
        assert by_name[ws.name]["subject_count"] == 1
        assert by_name["Personal"]["subject_count"] == 0
        assert body["total"] == 2

    async def test_excludes_archived_workspaces(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor
    ):
        ws, *_ = await _seed_tree(db_session, alice, archived=True)
        names = [
            w["name"] for w in (await _get(client, alice, "/dashboard/workspaces")).json()["data"]
        ]
        assert ws.name not in names

    async def test_cross_user(self, client: AsyncClient, db_session: AsyncSession, alice, bob):
        ws, *_ = await _seed_tree(db_session, alice)
        names = [
            w["name"] for w in (await _get(client, bob, "/dashboard/workspaces")).json()["data"]
        ]
        assert ws.name not in names

    async def test_limit_cap(self, client: AsyncClient, alice: Actor):
        assert (await _get(client, alice, "/dashboard/workspaces?limit=101")).status_code == 422


class TestRecentSubjects:
    async def test_requires_auth(self, client: AsyncClient):
        assert (await client.get("/api/v1/dashboard/recent-subjects")).status_code == 401

    async def test_empty(self, client: AsyncClient, alice: Actor):
        body = (await _get(client, alice, "/dashboard/recent-subjects")).json()
        assert body["success"] is True
        assert body["data"] == []

    async def test_returns_own_non_archived_most_recent_first(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor
    ):
        ws, first, *_ = await _seed_tree(db_session, alice)
        second = Subject(workspace_id=ws.id, name="Newer")
        db_session.add(second)
        db_session.add(Subject(workspace_id=ws.id, name="Gone", archived_at=datetime.now(UTC)))
        await db_session.commit()
        await db_session.refresh(second)
        data = (await _get(client, alice, "/dashboard/recent-subjects")).json()["data"]
        names = [s["name"] for s in data]
        assert "Gone" not in names
        assert names[0] == "Newer"
        assert data[0]["workspace_name"] == ws.name
        assert data[0]["workspace_id"] == str(ws.id)

    async def test_hides_subjects_of_archived_workspace(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor
    ):
        await _seed_tree(db_session, alice, archived=True)
        assert (await _get(client, alice, "/dashboard/recent-subjects")).json()["data"] == []

    async def test_cross_user(self, client: AsyncClient, db_session: AsyncSession, alice, bob):
        await _seed_tree(db_session, alice)
        assert (await _get(client, bob, "/dashboard/recent-subjects")).json()["data"] == []

    async def test_limit_cap(self, client: AsyncClient, alice: Actor):
        assert (await _get(client, alice, "/dashboard/recent-subjects?limit=21")).status_code == 422


class TestArchived:
    async def test_requires_auth(self, client: AsyncClient):
        assert (await client.get("/api/v1/dashboard/archived")).status_code == 401

    async def test_empty(self, client: AsyncClient, alice: Actor):
        body = (await _get(client, alice, "/dashboard/archived")).json()
        assert body == {"success": True, "data": [], "total": 0}

    async def test_lists_all_four_types_with_parent_context(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor
    ):
        ws, subject, folder, chapter = await _seed_tree(db_session, alice, archived=True)
        body = (await _get(client, alice, "/dashboard/archived")).json()
        assert body["total"] == 4
        by_type = {i["type"]: i for i in body["data"]}
        assert set(by_type) == {"workspace", "subject", "folder", "chapter"}
        assert by_type["workspace"]["id"] == str(ws.id)
        assert by_type["workspace"]["subject_id"] is None
        assert by_type["subject"]["workspace_id"] == str(ws.id)
        assert by_type["folder"]["id"] == str(folder.id)
        assert by_type["folder"]["subject_id"] == str(subject.id)
        assert by_type["chapter"]["name"] == "Limits"
        assert by_type["chapter"]["subject_name"] == "Maths"

    async def test_excludes_non_archived(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor
    ):
        await _seed_tree(db_session, alice, archived=False)
        assert (await _get(client, alice, "/dashboard/archived")).json()["total"] == 0

    async def test_pagination(self, client: AsyncClient, db_session: AsyncSession, alice: Actor):
        await _seed_tree(db_session, alice, archived=True)
        page1 = (await _get(client, alice, "/dashboard/archived?limit=3&offset=0")).json()
        page2 = (await _get(client, alice, "/dashboard/archived?limit=3&offset=3")).json()
        assert page1["total"] == page2["total"] == 4
        assert len(page1["data"]) == 3 and len(page2["data"]) == 1
        ids = {i["id"] for i in page1["data"]} | {i["id"] for i in page2["data"]}
        assert len(ids) == 4

    async def test_limit_cap(self, client: AsyncClient, alice: Actor):
        assert (await _get(client, alice, "/dashboard/archived?limit=101")).status_code == 422

    async def test_cross_user(self, client: AsyncClient, db_session: AsyncSession, alice, bob):
        await _seed_tree(db_session, alice, archived=True)
        body = (await _get(client, bob, "/dashboard/archived")).json()
        assert body["total"] == 0
        assert body["data"] == []


class TestWorkspaceLifecycleResponses:
    """Archive, restore and set-default must return the updated workspace (regression: a 500
    occurred because the server-updated updated_at was lazily loaded while serialising)."""

    async def test_archive_restore_and_set_default(self, client: AsyncClient, alice: Actor):
        base = {"cookies": alice.cookies, "headers": alice.headers}
        ws = (await client.post("/api/v1/workspaces", json={"name": "Cycle"}, **base)).json()[
            "data"
        ]

        archived = await client.post(f"/api/v1/workspaces/{ws['id']}/archive", **base)
        assert archived.status_code == 200
        assert archived.json()["data"]["archived_at"] is not None

        restored = await client.post(f"/api/v1/workspaces/{ws['id']}/restore", **base)
        assert restored.status_code == 200
        assert restored.json()["data"]["archived_at"] is None

        default = await client.post(f"/api/v1/workspaces/{ws['id']}/set-default", **base)
        assert default.status_code == 200
        assert default.json()["data"]["is_default"] is True

    async def test_other_user_cannot_archive_or_restore(
        self, client: AsyncClient, alice: Actor, bob: Actor
    ):
        ws = (
            await client.post(
                "/api/v1/workspaces",
                json={"name": "Mine"},
                cookies=alice.cookies,
                headers=alice.headers,
            )
        ).json()["data"]
        for action in ("archive", "restore"):
            resp = await client.post(
                f"/api/v1/workspaces/{ws['id']}/{action}", cookies=bob.cookies, headers=bob.headers
            )
            assert resp.status_code == 404
