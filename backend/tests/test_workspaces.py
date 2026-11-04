"""Tests for B2: workspaces backend."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import _make_session, _make_user


@pytest.mark.asyncio
async def test_list_workspaces(client: AsyncClient, db_session: AsyncSession):
    user = await _make_user(db_session, email="ws_list@example.com")
    raw, csrf = await _make_session(db_session, user)
    await db_session.commit()

    resp = await client.get(
        "/api/v1/workspaces",
        cookies={"aw_session": raw, "csrf_token": csrf},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["total"] >= 1  # default "Personal" workspace created at registration


@pytest.mark.asyncio
async def test_create_workspace(client: AsyncClient, db_session: AsyncSession):
    user = await _make_user(db_session, email="ws_create@example.com")
    raw, csrf = await _make_session(db_session, user)
    await db_session.commit()

    resp = await client.post(
        "/api/v1/workspaces",
        json={"name": "University", "workspace_type": "university"},
        cookies={"aw_session": raw, "csrf_token": csrf},
        headers={"x-csrf-token": csrf},
    )
    assert resp.status_code == 201
    assert resp.json()["data"]["name"] == "University"


@pytest.mark.asyncio
async def test_create_workspace_duplicate_name(client: AsyncClient, db_session: AsyncSession):
    user = await _make_user(db_session, email="ws_dup@example.com")
    raw, csrf = await _make_session(db_session, user)
    await db_session.commit()

    for _ in range(2):
        resp = await client.post(
            "/api/v1/workspaces",
            json={"name": "Duplicate"},
            cookies={"aw_session": raw, "csrf_token": csrf},
            headers={"x-csrf-token": csrf},
        )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "WORKSPACE_NAME_CONFLICT"


@pytest.mark.asyncio
async def test_get_workspace_not_found(client: AsyncClient, db_session: AsyncSession):
    user = await _make_user(db_session, email="ws_notfound@example.com")
    raw, csrf = await _make_session(db_session, user)
    await db_session.commit()

    import uuid

    resp = await client.get(
        f"/api/v1/workspaces/{uuid.uuid4()}",
        cookies={"aw_session": raw, "csrf_token": csrf},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cross_user_workspace_access_denied(client: AsyncClient, db_session: AsyncSession):
    """User B cannot access User A's workspace."""
    user_a = await _make_user(db_session, email="ws_owner@example.com")
    user_b = await _make_user(db_session, email="ws_other@example.com")

    raw_b, csrf_b = await _make_session(db_session, user_b)
    await db_session.commit()

    # Get user_a's workspace id
    from sqlalchemy import select

    from app.models.workspace import Workspace

    result = await db_session.execute(select(Workspace).where(Workspace.user_id == user_a.id))
    ws_a = result.scalar_one()

    resp = await client.get(
        f"/api/v1/workspaces/{ws_a.id}",
        cookies={"aw_session": raw_b, "csrf_token": csrf_b},
    )
    assert resp.status_code == 404  # must not leak existence


@pytest.mark.asyncio
async def test_workspaces_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/workspaces")
    assert resp.status_code == 401
