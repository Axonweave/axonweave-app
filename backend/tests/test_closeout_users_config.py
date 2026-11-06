"""Closeout tests: change-email flow, data export, sessions, password change, account deletion,
production configuration guards, email template escaping, workspace service edge cases."""

import re

import pytest
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.email import ConsoleEmailSender, InMemoryEmailSender, get_email_sender
from app.core.email_templates import (
    email_change_email,
    password_reset_email,
    verification_email,
)
from app.main import app
from app.models.activity_log import ActivityLog
from app.models.user import User
from tests.conftest import _make_session, _make_user

PASSWORD = "TestPassword123!"


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
    return await _actor(db_session, "alice-close@example.com")


@pytest.fixture
async def bob(db_session: AsyncSession) -> Actor:
    return await _actor(db_session, "bob-close@example.com")


@pytest.fixture
def mailbox():
    sender = InMemoryEmailSender()
    app.dependency_overrides[get_email_sender] = lambda: sender
    yield sender
    app.dependency_overrides.pop(get_email_sender, None)


async def _call(client: AsyncClient, who: Actor, method: str, url: str, **kw):
    return await client.request(
        method, f"/api/v1{url}", cookies=who.cookies, headers=who.headers, **kw
    )


class TestChangeEmail:
    async def test_full_flow_sends_link_to_new_address_and_applies_on_verify(
        self, client: AsyncClient, alice: Actor, mailbox: InMemoryEmailSender
    ):
        resp = await _call(
            client,
            alice,
            "POST",
            "/users/me/change-email",
            json={"new_email": "New.Address@Example.com", "current_password": PASSWORD},
        )
        assert resp.status_code == 200
        assert len(mailbox.sent) == 1
        assert mailbox.sent[0]["to"] == "new.address@example.com"

        # Not applied until the link is used
        me = (await _call(client, alice, "GET", "/auth/me")).json()["data"]
        assert me["email"] == "alice-close@example.com"

        token = re.search(r"token=([\w-]+)", mailbox.sent[0]["text"]).group(1)
        verify = await client.post("/api/v1/auth/verify-email", json={"token": token})
        assert verify.status_code == 200
        me = (await _call(client, alice, "GET", "/auth/me")).json()["data"]
        assert me["email"] == "new.address@example.com"

        # Single use
        again = await client.post("/api/v1/auth/verify-email", json={"token": token})
        assert again.status_code == 400

    async def test_wrong_password_rejected_and_nothing_sent(
        self, client: AsyncClient, alice: Actor, mailbox: InMemoryEmailSender
    ):
        resp = await _call(
            client,
            alice,
            "POST",
            "/users/me/change-email",
            json={"new_email": "x@example.com", "current_password": "WrongPassword!"},
        )
        assert resp.status_code == 400
        assert mailbox.sent == []

    async def test_existing_email_rejected(
        self, client: AsyncClient, alice: Actor, bob: Actor, mailbox: InMemoryEmailSender
    ):
        resp = await _call(
            client,
            alice,
            "POST",
            "/users/me/change-email",
            json={"new_email": "bob-close@example.com", "current_password": PASSWORD},
        )
        assert resp.status_code == 409
        assert mailbox.sent == []

    async def test_unverified_user_cannot_change_email(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        alice: Actor,
        mailbox: InMemoryEmailSender,
    ):
        alice.user.is_verified = False
        db_session.add(alice.user)
        await db_session.commit()
        resp = await _call(
            client,
            alice,
            "POST",
            "/users/me/change-email",
            json={"new_email": "z@example.com", "current_password": PASSWORD},
        )
        assert resp.status_code == 403

    async def test_email_taken_between_request_and_confirmation(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        alice: Actor,
        mailbox: InMemoryEmailSender,
    ):
        await _call(
            client,
            alice,
            "POST",
            "/users/me/change-email",
            json={"new_email": "late@example.com", "current_password": PASSWORD},
        )
        await _make_user(db_session, email="late@example.com")
        await db_session.commit()
        token = re.search(r"token=([\w-]+)", mailbox.sent[0]["text"]).group(1)
        resp = await client.post("/api/v1/auth/verify-email", json={"token": token})
        assert resp.status_code == 409


class TestEmailTemplatesAndSender:
    def test_user_supplied_name_is_html_escaped(self):
        evil = '<script>alert(1)</script>"'
        for html, _text in (
            verification_email(evil, "https://x.example/v?token=a"),
            password_reset_email(evil, "https://x.example/r?token=a"),
            email_change_email(evil, "https://x.example/c?token=a"),
        ):
            assert "<script>" not in html
            assert "&lt;script&gt;" in html

    async def test_console_sender_does_not_log_bodies_outside_development(self, monkeypatch):
        from structlog.testing import capture_logs

        from app.core import email as email_module
        from app.core.config import AppEnv

        monkeypatch.setattr(email_module.settings, "app_env", AppEnv.production, raising=False)
        with capture_logs() as logs:
            await ConsoleEmailSender().send(
                "someone@example.com", "Subject", "<p>html</p>", "https://x/v?token=SECRET"
            )
        assert logs
        assert "SECRET" not in str(logs)
        assert "someone@example.com" not in str(logs)


_BASE = {
    "app_env": "production",
    "app_secret_key": "x" * 40,
    "database_url": "postgresql+psycopg://u:realpass@db:5432/app",
    "database_migration_url": "postgresql+psycopg://o:realpass@db:5432/app",
    "frontend_url": "https://app.example.com",
    "cookie_secure": True,
}


class TestProductionConfigGuards:
    def _make(self, **over):
        return Settings(_env_file=None, **{**_BASE, **over})

    def test_valid_production_config_starts(self):
        assert self._make().app_env == "production"

    def test_missing_secret_key_refuses_to_start(self, monkeypatch):
        # CI sets APP_SECRET_KEY in the environment; "missing" must mean missing everywhere.
        monkeypatch.delenv("APP_SECRET_KEY", raising=False)
        data = {k: v for k, v in _BASE.items() if k != "app_secret_key"}
        with pytest.raises(ValidationError):
            Settings(_env_file=None, **data)

    def test_short_secret_key_refused(self):
        with pytest.raises(ValidationError):
            self._make(app_secret_key="short")

    @pytest.mark.parametrize(
        "secret", ["replace_with_secure_random_string_minimum_32_chars", "change_me" + "x" * 30]
    )
    def test_placeholder_secret_refused(self, secret):
        with pytest.raises(ValidationError, match="placeholder"):
            self._make(app_secret_key=secret)

    def test_insecure_cookies_refused(self):
        with pytest.raises(ValidationError, match="COOKIE_SECURE"):
            self._make(cookie_secure=False)

    def test_http_frontend_refused(self):
        with pytest.raises(ValidationError, match="https"):
            self._make(frontend_url="http://app.example.com")

    def test_placeholder_database_password_refused(self):
        with pytest.raises(ValidationError, match="placeholder"):
            self._make(database_url="postgresql+psycopg://u:replace_me@db:5432/app")

    def test_development_allows_local_defaults(self):
        s = self._make(
            app_env="development", cookie_secure=False, frontend_url="http://localhost:3000"
        )
        assert s.app_env == "development"


class TestSessionsAndPassword:
    async def test_list_and_revoke_own_session_but_not_others(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, bob: Actor
    ):
        extra_token, _ = await _make_session(db_session, alice.user)
        await db_session.commit()
        sessions = (await _call(client, alice, "GET", "/users/me/sessions")).json()["data"]
        assert len(sessions) == 2
        other = next(s for s in sessions if not s.get("is_current"))

        bob_sessions = (await _call(client, bob, "GET", "/users/me/sessions")).json()["data"]
        foreign = await _call(client, bob, "DELETE", f"/users/me/sessions/{sessions[0]['id']}")
        assert foreign.status_code == 404
        assert all(s["id"] not in {x["id"] for x in sessions} for s in bob_sessions)

        revoked = await _call(client, alice, "DELETE", f"/users/me/sessions/{other['id']}")
        assert revoked.status_code == 200
        gone = await client.get("/api/v1/auth/me", cookies={"aw_session": extra_token})
        assert gone.status_code == 401

    async def test_change_password_keeps_current_session_and_revokes_others(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor
    ):
        other_token, _ = await _make_session(db_session, alice.user)
        await db_session.commit()
        resp = await _call(
            client,
            alice,
            "POST",
            "/users/me/change-password",
            json={"current_password": PASSWORD, "new_password": "BrandNewPassword99!"},
        )
        assert resp.status_code == 200
        assert (await _call(client, alice, "GET", "/auth/me")).status_code == 200
        assert (
            await client.get("/api/v1/auth/me", cookies={"aw_session": other_token})
        ).status_code == 401

    async def test_preferences_roundtrip_and_invalid_theme_rejected(
        self, client: AsyncClient, alice: Actor
    ):
        ok = await _call(client, alice, "PATCH", "/users/me/preferences", json={"theme": "dark"})
        assert ok.status_code == 200
        assert (await _call(client, alice, "GET", "/users/me/preferences")).json()["data"][
            "theme"
        ] == "dark"
        bad = await _call(client, alice, "PATCH", "/users/me/preferences", json={"theme": "neon"})
        assert bad.status_code == 422


class TestExportAndDeletion:
    async def test_export_contains_own_academic_data_only(
        self, client: AsyncClient, alice: Actor, bob: Actor
    ):
        await _call(client, alice, "POST", "/workspaces", json={"name": "Alice Uni"})
        await _call(client, bob, "POST", "/workspaces", json={"name": "Bob Secret"})
        resp = await _call(client, alice, "GET", "/users/me/export")
        assert resp.status_code == 200
        assert "attachment" in resp.headers["content-disposition"]
        data = resp.json()["data"]
        names = [w["name"] for w in data["workspaces"]]
        assert "Alice Uni" in names and "Bob Secret" not in names
        assert set(data) >= {
            "profile",
            "preferences",
            "workspaces",
            "subjects",
            "folders",
            "chapters",
            "activity",
        }
        assert "password" not in resp.text.lower()
        assert any(a["entity_name"] == "Alice Uni" for a in data["activity"])

    async def test_export_is_rate_limited(self, client: AsyncClient, alice: Actor):
        codes = [
            (await _call(client, alice, "GET", "/users/me/export")).status_code for _ in range(3)
        ]
        assert codes[:2] == [200, 200] and codes[2] == 429

    async def test_delete_account_removes_user_and_data_and_ends_session(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor
    ):
        user_id = alice.user.id
        await _call(client, alice, "POST", "/workspaces", json={"name": "Doomed"})
        resp = await _call(
            client,
            alice,
            "DELETE",
            "/users/me",
            json={"password": PASSWORD, "confirmation": "delete my account"},
        )
        assert resp.status_code == 200
        db_session.expire_all()
        assert (
            await db_session.execute(select(User).where(User.id == user_id))
        ).scalar_one_or_none() is None
        assert (
            await db_session.execute(select(ActivityLog).where(ActivityLog.user_id == user_id))
        ).first() is None
        assert (await client.get("/api/v1/auth/me", cookies=alice.cookies)).status_code == 401

    async def test_delete_requires_typed_confirmation(self, client: AsyncClient, alice: Actor):
        resp = await _call(
            client,
            alice,
            "DELETE",
            "/users/me",
            json={"password": PASSWORD, "confirmation": "yes"},
        )
        assert resp.status_code == 422


class TestWorkspaceServiceEdges:
    async def _create(self, client, who, name):
        return (await _call(client, who, "POST", "/workspaces", json={"name": name})).json()["data"]

    async def test_update_and_name_conflict(self, client: AsyncClient, alice: Actor):
        a = await self._create(client, alice, "Alpha")
        b = await self._create(client, alice, "Beta")
        ok = await _call(
            client,
            alice,
            "PATCH",
            f"/workspaces/{a['id']}",
            json={
                "name": "Alpha 2",
                "description": "d",
                "workspace_type": "research",
                "colour": "#112233",
            },
        )
        assert ok.status_code == 200 and ok.json()["data"]["workspace_type"] == "research"
        clash = await _call(
            client, alice, "PATCH", f"/workspaces/{b['id']}", json={"name": "alpha 2"}
        )
        assert clash.status_code == 409

    async def test_default_workspace_cannot_be_archived_or_deleted(
        self, client: AsyncClient, alice: Actor
    ):
        listing = (await _call(client, alice, "GET", "/workspaces")).json()["data"]
        default = next(w for w in listing if w["is_default"])
        assert (
            await _call(client, alice, "POST", f"/workspaces/{default['id']}/archive")
        ).status_code == 409
        assert (
            await _call(client, alice, "DELETE", f"/workspaces/{default['id']}")
        ).status_code == 409

    async def test_restore_conflicts_and_not_archived(self, client: AsyncClient, alice: Actor):
        ws = await self._create(client, alice, "Cycle")
        assert (
            await _call(client, alice, "POST", f"/workspaces/{ws['id']}/restore")
        ).status_code == 409
        await _call(client, alice, "POST", f"/workspaces/{ws['id']}/archive")
        await self._create(client, alice, "Cycle")  # same name now free (D-11: non-archived only)
        clash = await _call(client, alice, "POST", f"/workspaces/{ws['id']}/restore")
        assert clash.status_code == 409
        assert clash.json()["error"]["code"] == "WORKSPACE_NAME_CONFLICT"

    async def test_restore_of_other_users_workspace_is_404(
        self, client: AsyncClient, alice: Actor, bob: Actor
    ):
        ws = await self._create(client, alice, "Mine")
        await _call(client, alice, "POST", f"/workspaces/{ws['id']}/archive")
        assert (
            await _call(client, bob, "POST", f"/workspaces/{ws['id']}/restore")
        ).status_code == 404
        assert (await _call(client, bob, "DELETE", f"/workspaces/{ws['id']}")).status_code == 404
        assert (
            await _call(client, bob, "PATCH", f"/workspaces/{ws['id']}", json={"name": "x"})
        ).status_code == 404
