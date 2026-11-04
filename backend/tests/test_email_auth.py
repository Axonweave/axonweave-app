"""Tests for A3: email verification and password reset flows."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import generate_token, hash_token
from app.models.email_verification_token import EmailVerificationToken
from app.models.password_reset_token import PasswordResetToken
from tests.conftest import _make_user

# ── Helpers ───────────────────────────────────────────────────────────────────


async def _create_verify_token(db: AsyncSession, user_id, *, expired: bool = False) -> str:
    raw = generate_token()
    token_hash = hash_token(raw)
    now = datetime.now(UTC)
    ttl = timedelta(hours=-1) if expired else timedelta(hours=24)
    token = EmailVerificationToken(
        user_id=user_id,
        token_hash=token_hash,
        purpose="verify_email",
        expires_at=now + ttl,
        created_at=now,
    )
    db.add(token)
    await db.flush()
    return raw


async def _create_reset_token(db: AsyncSession, user_id, *, expired: bool = False) -> str:
    raw = generate_token()
    token_hash = hash_token(raw)
    now = datetime.now(UTC)
    ttl = timedelta(minutes=-1) if expired else timedelta(minutes=30)
    token = PasswordResetToken(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=now + ttl,
        created_at=now,
    )
    db.add(token)
    await db.flush()
    return raw


# ── Email verification ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_verify_email_success(client: AsyncClient, db_session: AsyncSession):
    user = await _make_user(db_session, email="unverified@example.com")
    user.is_verified = False
    user.email_verified_at = None
    user.status = "pending_verification"
    await db_session.flush()

    raw = await _create_verify_token(db_session, user.id)
    await db_session.commit()

    resp = await client.post("/api/v1/auth/verify-email", json={"token": raw})
    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_verify_email_expired_token(client: AsyncClient, db_session: AsyncSession):
    user = await _make_user(db_session, email="expired_verify@example.com")
    user.is_verified = False
    user.status = "pending_verification"
    await db_session.flush()

    raw = await _create_verify_token(db_session, user.id, expired=True)
    await db_session.commit()

    resp = await client.post("/api/v1/auth/verify-email", json={"token": raw})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_TOKEN"


@pytest.mark.asyncio
async def test_verify_email_invalid_token(client: AsyncClient):
    resp = await client.post("/api/v1/auth/verify-email", json={"token": "notarealtoken"})
    assert resp.status_code == 400


# ── Password reset ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_forgot_password_always_returns_200(client: AsyncClient):
    """Must return 200 regardless of whether the email exists."""
    resp = await client.post("/api/v1/auth/forgot-password", json={"email": "nobody@example.com"})
    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_reset_password_success(client: AsyncClient, db_session: AsyncSession):
    user = await _make_user(db_session, email="resetme@example.com")
    raw = await _create_reset_token(db_session, user.id)
    await db_session.commit()

    resp = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": raw, "new_password": "NewValidPass999!"},
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_reset_password_expired_token(client: AsyncClient, db_session: AsyncSession):
    user = await _make_user(db_session, email="expired_reset@example.com")
    raw = await _create_reset_token(db_session, user.id, expired=True)
    await db_session.commit()

    resp = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": raw, "new_password": "NewValidPass999!"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_TOKEN"


@pytest.mark.asyncio
async def test_reset_password_too_short(client: AsyncClient, db_session: AsyncSession):
    user = await _make_user(db_session, email="shortpw_reset@example.com")
    raw = await _create_reset_token(db_session, user.id)
    await db_session.commit()

    resp = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": raw, "new_password": "short"},
    )
    assert resp.status_code == 422
