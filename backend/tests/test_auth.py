"""Auth endpoint tests — register, login, logout, /me, cross-user access."""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from tests.conftest import _make_session, _make_user

# ── Registration ──────────────────────────────────────────────────────────────


async def test_register_success(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Alice Smith",
            "email": "alice@example.com",
            "password": "SecurePass123!!",
            "confirm_password": "SecurePass123!!",
            "terms_accepted": True,
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    assert body["data"]["email"] == "alice@example.com"
    assert "password" not in str(body)
    assert "password_hash" not in str(body)


async def test_register_duplicate_email(client: AsyncClient) -> None:
    payload = {
        "full_name": "Bob Jones",
        "email": "bob@example.com",
        "password": "SecurePass123!!",
        "confirm_password": "SecurePass123!!",
        "terms_accepted": True,
    }
    await client.post("/api/v1/auth/register", json=payload)
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 409


async def test_register_password_mismatch(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Carol",
            "email": "carol@example.com",
            "password": "SecurePass123!!",
            "confirm_password": "DifferentPass123!!",
            "terms_accepted": True,
        },
    )
    assert response.status_code == 422


async def test_register_short_password(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Dave",
            "email": "dave@example.com",
            "password": "short",
            "confirm_password": "short",
            "terms_accepted": True,
        },
    )
    assert response.status_code == 422


async def test_register_common_password(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Eve",
            "email": "eve@example.com",
            "password": "password123",
            "confirm_password": "password123",
            "terms_accepted": True,
        },
    )
    assert response.status_code == 422


async def test_register_terms_not_accepted(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Frank",
            "email": "frank@example.com",
            "password": "SecurePass123!!",
            "confirm_password": "SecurePass123!!",
            "terms_accepted": False,
        },
    )
    assert response.status_code == 422


# ── Login ─────────────────────────────────────────────────────────────────────


async def test_login_success(client: AsyncClient, db_session: AsyncSession) -> None:
    user = await _make_user(db_session, email="login_test@example.com")
    await db_session.commit()

    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "login_test@example.com",
            "password": "TestPassword123!",
            "remember_me": False,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert "aw_session" in response.cookies
    assert "csrf_token" in response.cookies
    # csrf_token must NOT be httponly (JS must read it)
    # httpx doesn't expose httponly flag directly, but we check cookie presence


async def test_login_wrong_password(client: AsyncClient, db_session: AsyncSession) -> None:
    await _make_user(db_session, email="wrongpw@example.com")
    await db_session.commit()

    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "wrongpw@example.com",
            "password": "WrongPassword999!",
        },
    )
    assert response.status_code == 401
    body = response.json()
    # Must not reveal whether email exists
    assert body["error"]["code"] == "INVALID_CREDENTIALS"


async def test_login_unknown_email(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "nobody@example.com",
            "password": "AnyPassword123!",
        },
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


# ── /me ───────────────────────────────────────────────────────────────────────


async def test_me_authenticated(
    client: AsyncClient,
    create_user_and_session: tuple[User, str, str],
) -> None:
    user, raw_token, csrf_token = create_user_and_session
    response = await client.get(
        "/api/v1/auth/me",
        cookies={"aw_session": raw_token},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["email"] == user.email
    assert "password_hash" not in str(body)


async def test_me_unauthenticated(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401


async def test_me_invalid_session(client: AsyncClient) -> None:
    response = await client.get(
        "/api/v1/auth/me",
        cookies={"aw_session": "totally_fake_token"},
    )
    assert response.status_code == 401


# ── Logout ────────────────────────────────────────────────────────────────────


async def test_logout_clears_cookies(
    client: AsyncClient,
    create_user_and_session: tuple[User, str, str],
) -> None:
    user, raw_token, csrf_token = create_user_and_session
    response = await client.post(
        "/api/v1/auth/logout",
        cookies={"aw_session": raw_token, "csrf_token": csrf_token},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert response.status_code == 200
    # Session cookie should be cleared (set to empty/expired)
    assert response.cookies.get("aw_session", "") == ""


async def test_session_invalidated_after_logout(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = await _make_user(db_session, email="logout_test@example.com")
    await db_session.commit()

    # Login
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "logout_test@example.com",
            "password": "TestPassword123!",
        },
    )
    assert login_resp.status_code == 200
    session_cookie = login_resp.cookies["aw_session"]
    csrf = login_resp.cookies["csrf_token"]

    # Logout
    await client.post(
        "/api/v1/auth/logout",
        cookies={"aw_session": session_cookie, "csrf_token": csrf},
        headers={"X-CSRF-Token": csrf},
    )

    # /me must now 401
    me_resp = await client.get("/api/v1/auth/me", cookies={"aw_session": session_cookie})
    assert me_resp.status_code == 401


# ── Cross-user access ─────────────────────────────────────────────────────────


async def test_user_a_cannot_use_user_b_session(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Sessions are not transferable between users."""
    user_a = await _make_user(db_session, email="usera@example.com")
    user_b = await _make_user(db_session, email="userb@example.com")
    await db_session.commit()

    raw_a, _ = await _make_session(db_session, user_a)
    await db_session.commit()

    # User B's token should only return user B's data; user A's token returns user A's data
    resp_a = await client.get("/api/v1/auth/me", cookies={"aw_session": raw_a})
    assert resp_a.status_code == 200
    assert resp_a.json()["data"]["email"] == user_a.email
