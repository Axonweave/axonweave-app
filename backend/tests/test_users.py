"""Tests for A5: users API (profile, preferences, sessions, password change, deletion)."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import _make_session, _make_user


async def _auth_headers(raw_token: str, csrf: str) -> dict[str, str]:
    return {"x-csrf-token": csrf, "cookie": f"aw_session={raw_token}; csrf_token={csrf}"}


@pytest.mark.asyncio
async def test_get_profile(client: AsyncClient, db_session: AsyncSession):
    user = await _make_user(db_session, email="profile_get@example.com", full_name="Alice Test")
    raw, csrf = await _make_session(db_session, user)
    await db_session.commit()

    resp = await client.get(
        "/api/v1/users/me/profile",
        cookies={"aw_session": raw, "csrf_token": csrf},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["full_name"] == "Alice Test"


@pytest.mark.asyncio
async def test_update_profile(client: AsyncClient, db_session: AsyncSession):
    user = await _make_user(db_session, email="profile_update@example.com")
    raw, csrf = await _make_session(db_session, user)
    await db_session.commit()

    resp = await client.patch(
        "/api/v1/users/me/profile",
        json={"full_name": "Bob Updated"},
        cookies={"aw_session": raw, "csrf_token": csrf},
        headers={"x-csrf-token": csrf},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["full_name"] == "Bob Updated"


@pytest.mark.asyncio
async def test_list_sessions(client: AsyncClient, db_session: AsyncSession):
    user = await _make_user(db_session, email="sessions_list@example.com")
    raw, csrf = await _make_session(db_session, user)
    await db_session.commit()

    resp = await client.get(
        "/api/v1/users/me/sessions",
        cookies={"aw_session": raw, "csrf_token": csrf},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) >= 1
    current = [s for s in data if s["is_current"]]
    assert len(current) == 1


@pytest.mark.asyncio
async def test_change_password_wrong_current(client: AsyncClient, db_session: AsyncSession):
    user = await _make_user(db_session, email="change_pw_bad@example.com")
    raw, csrf = await _make_session(db_session, user)
    await db_session.commit()

    resp = await client.post(
        "/api/v1/users/me/change-password",
        json={"current_password": "WrongPassword!", "new_password": "NewValidPass999!"},
        cookies={"aw_session": raw, "csrf_token": csrf},
        headers={"x-csrf-token": csrf},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_PASSWORD"


@pytest.mark.asyncio
async def test_change_password_success(client: AsyncClient, db_session: AsyncSession):
    user = await _make_user(db_session, email="change_pw_ok@example.com")
    raw, csrf = await _make_session(db_session, user)
    await db_session.commit()

    resp = await client.post(
        "/api/v1/users/me/change-password",
        json={"current_password": "TestPassword123!", "new_password": "NewValidPass999!"},
        cookies={"aw_session": raw, "csrf_token": csrf},
        headers={"x-csrf-token": csrf},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_delete_account_wrong_password(client: AsyncClient, db_session: AsyncSession):
    user = await _make_user(db_session, email="delete_bad@example.com")
    raw, csrf = await _make_session(db_session, user)
    await db_session.commit()

    resp = await client.request(
        "DELETE",
        "/api/v1/users/me",
        json={"password": "WrongPassword!", "confirmation": "delete my account"},
        cookies={"aw_session": raw, "csrf_token": csrf},
        headers={"x-csrf-token": csrf},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_profile_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/users/me/profile")
    assert resp.status_code == 401
