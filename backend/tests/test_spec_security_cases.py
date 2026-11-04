"""Spec 19.2 essential security cases that were not explicitly covered elsewhere.

Maps to docs/SECURITY_REVIEW.md:
  case 2  -> TestCrossUserMutations.test_user_cannot_edit_other_users_subject
  case 3  -> TestCrossUserMutations.test_user_cannot_delete_other_users_chapter
  case 7  -> TestResetTokens.test_unknown_reset_token_rejected
  case 8  -> TestResetTokens.test_reset_token_cannot_be_reused
  case 11 -> TestCsrf.*
"""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import generate_token, hash_token
from app.models.chapter import Chapter
from app.models.password_reset_token import PasswordResetToken
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
    return await _actor(db_session, "alice-sec@example.com")


@pytest.fixture
async def bob(db_session: AsyncSession) -> Actor:
    return await _actor(db_session, "bob-sec@example.com")


async def _bobs_tree(db: AsyncSession, bob: Actor):
    ws = Workspace(user_id=bob.user.id, name="Bob WS", workspace_type="custom", is_default=False)
    db.add(ws)
    await db.flush()
    subject = Subject(workspace_id=ws.id, name="Bob Subject")
    db.add(subject)
    await db.flush()
    chapter = Chapter(subject_id=subject.id, title="Bob Chapter")
    db.add(chapter)
    await db.commit()
    return ws, subject, chapter


class TestCrossUserMutations:
    async def test_user_cannot_edit_other_users_subject(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, bob: Actor
    ):
        ws, subject, _ = await _bobs_tree(db_session, bob)
        url = f"/api/v1/workspaces/{ws.id}/subjects/{subject.id}"
        resp = await client.patch(
            url, json={"name": "Hijacked"}, cookies=alice.cookies, headers=alice.headers
        )
        assert resp.status_code == 404
        # Bob's data is untouched
        check = await client.get(url, cookies=bob.cookies, headers=bob.headers)
        assert check.json()["data"]["name"] == "Bob Subject"

    async def test_user_cannot_delete_other_users_chapter(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, bob: Actor
    ):
        ws, subject, chapter = await _bobs_tree(db_session, bob)
        url = f"/api/v1/workspaces/{ws.id}/subjects/{subject.id}/chapters/{chapter.id}"
        resp = await client.delete(url, cookies=alice.cookies, headers=alice.headers)
        assert resp.status_code == 404
        still_there = await client.get(url, cookies=bob.cookies, headers=bob.headers)
        assert still_there.status_code == 200

    async def test_user_cannot_archive_restore_or_delete_other_users_subject(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, bob: Actor
    ):
        ws, subject, _ = await _bobs_tree(db_session, bob)
        base = f"/api/v1/workspaces/{ws.id}/subjects/{subject.id}"
        for method, url in (
            ("POST", f"{base}/archive"),
            ("POST", f"{base}/restore"),
            ("DELETE", base),
        ):
            resp = await client.request(method, url, cookies=alice.cookies, headers=alice.headers)
            assert resp.status_code == 404, (method, url)


async def _reset_token(db: AsyncSession, user_id) -> str:
    raw = generate_token()
    now = datetime.now(UTC)
    db.add(
        PasswordResetToken(
            user_id=user_id,
            token_hash=hash_token(raw),
            expires_at=now + timedelta(minutes=30),
            created_at=now,
        )
    )
    await db.commit()
    return raw


class TestResetTokens:
    async def test_unknown_reset_token_rejected(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/auth/reset-password",
            json={"token": generate_token(), "new_password": "AnotherValidPass99!"},
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "INVALID_TOKEN"

    async def test_reset_token_cannot_be_reused(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor
    ):
        raw = await _reset_token(db_session, alice.user.id)
        first = await client.post(
            "/api/v1/auth/reset-password",
            json={"token": raw, "new_password": "FirstNewPass1234!"},
        )
        assert first.status_code == 200
        second = await client.post(
            "/api/v1/auth/reset-password",
            json={"token": raw, "new_password": "SecondNewPass1234!"},
        )
        assert second.status_code == 400
        assert second.json()["error"]["code"] == "INVALID_TOKEN"

    async def test_reset_revokes_existing_sessions(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor
    ):
        raw = await _reset_token(db_session, alice.user.id)
        await client.post(
            "/api/v1/auth/reset-password",
            json={"token": raw, "new_password": "FirstNewPass1234!"},
        )
        resp = await client.get("/api/v1/auth/me", cookies=alice.cookies)
        assert resp.status_code == 401


class TestCsrf:
    async def test_cross_origin_request_with_valid_token_is_rejected(
        self, client: AsyncClient, alice: Actor
    ):
        resp = await client.post(
            "/api/v1/workspaces",
            json={"name": "Evil"},
            cookies=alice.cookies,
            headers={**alice.headers, "Origin": "https://evil.example"},
        )
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "CSRF_ORIGIN_MISMATCH"

    async def test_state_change_without_token_header_is_rejected(
        self, client: AsyncClient, alice: Actor
    ):
        resp = await client.post(
            "/api/v1/workspaces", json={"name": "NoToken"}, cookies=alice.cookies
        )
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "CSRF_TOKEN_MISSING"

    async def test_state_change_with_mismatched_token_is_rejected(
        self, client: AsyncClient, alice: Actor
    ):
        resp = await client.post(
            "/api/v1/workspaces",
            json={"name": "Mismatch"},
            cookies=alice.cookies,
            headers={"X-CSRF-Token": "not-the-cookie-value"},
        )
        assert resp.status_code == 403

    async def test_cors_does_not_allow_foreign_origin(self, client: AsyncClient):
        resp = await client.options(
            "/api/v1/workspaces",
            headers={
                "Origin": "https://evil.example",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert resp.headers.get("access-control-allow-origin") != "https://evil.example"
        assert resp.headers.get("access-control-allow-origin") != "*"


class TestRateLimitIpSpoofing:
    """Spec 19.2 case 12: rate limits are enforced, and cannot be dodged by spoofing headers."""

    async def test_spoofed_forwarded_for_does_not_bypass_register_limit(self, client: AsyncClient):
        statuses = []
        for i in range(15):
            resp = await client.post(
                "/api/v1/auth/register",
                json={
                    "full_name": "Spoof",
                    "email": f"spoof{i}@example.com",
                    "password": "ValidPassword123!",
                    "confirm_password": "ValidPassword123!",
                    "terms_accepted": True,
                },
                headers={"X-Forwarded-For": f"203.0.113.{i}"},
            )
            statuses.append(resp.status_code)
        assert 429 in statuses
