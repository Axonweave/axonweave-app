"""Users service — profile, preferences, sessions, password/email changes, export, deletion (A5)."""

import hashlib
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.security import hash_password, verify_password
from app.core.security_logging import (
    log_account_deletion_requested,
    log_email_change_requested,
    log_password_changed,
    log_session_revoked,
)
from app.models.session_model import Session
from app.models.user import User
from app.modules.users.schemas import (
    ChangeEmailRequest,
    ChangePasswordRequest,
    DeleteAccountRequest,
    UpdatePreferencesRequest,
    UpdateProfileRequest,
)
from app.repositories.session_repository import SessionRepository
from app.repositories.user_repository import UserRepository

logger = get_logger(__name__)


class UsersService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._users = UserRepository(db)
        self._sessions = SessionRepository(db)

    # ── Profile ───────────────────────────────────────────────────────────────

    async def update_profile(self, user: User, data: UpdateProfileRequest) -> User:
        profile = user.profile
        if profile is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "PROFILE_NOT_FOUND", "message": "Profile not found."},
            )
        if data.full_name is not None:
            profile.full_name = data.full_name
        if data.preferred_language is not None:
            profile.preferred_language = data.preferred_language
        if data.timezone is not None:
            profile.timezone = data.timezone
        await self._db.flush()
        return user

    # ── Preferences ───────────────────────────────────────────────────────────

    async def update_preferences(self, user: User, data: UpdatePreferencesRequest) -> User:
        prefs = user.preferences
        if prefs is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "PREFS_NOT_FOUND", "message": "Preferences not found."},
            )
        if data.theme is not None:
            prefs.theme = data.theme
        if data.explanation_style is not None:
            prefs.explanation_style = data.explanation_style
        if data.academic_level is not None:
            prefs.academic_level = data.academic_level
        if data.study_preferences is not None:
            prefs.study_preferences = data.study_preferences
        if data.preferred_language is not None:
            prefs.preferred_language = data.preferred_language
        await self._db.flush()
        return user

    # ── Sessions ─────────────────────────────────────────────────────────────

    async def list_sessions(self, user: User, current_token_hash: str | None) -> list[Session]:
        result = await self._db.execute(
            select(Session).where(
                Session.user_id == user.id,
                Session.revoked_at.is_(None),
                Session.expires_at > datetime.now(UTC),
            )
        )
        sessions = list(result.scalars().all())
        if current_token_hash:
            for s in sessions:
                s.is_current = s.session_token_hash == current_token_hash  # type: ignore[attr-defined]
        return sessions

    async def revoke_session(self, user: User, session_id: uuid.UUID, ip: str) -> None:
        result = await self._db.execute(
            select(Session).where(
                Session.id == session_id,
                Session.user_id == user.id,  # ownership check
                Session.revoked_at.is_(None),
            )
        )
        session = result.scalar_one_or_none()
        if session is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "SESSION_NOT_FOUND", "message": "Session not found."},
            )
        await self._sessions.revoke(session)
        log_session_revoked(str(user.id), "user_revoked")

    # ── Password change ───────────────────────────────────────────────────────

    async def change_password(
        self, user: User, data: ChangePasswordRequest, current_session_hash: str | None, ip: str
    ) -> None:
        """Re-authenticates (D-22), updates hash, revokes all other sessions."""
        if not verify_password(data.current_password, user.password_hash):
            raise HTTPException(
                status_code=400,
                detail={"code": "INVALID_PASSWORD", "message": "Current password is incorrect."},
            )
        user.password_hash = hash_password(data.new_password)

        # Revoke all sessions except the current one
        result = await self._db.execute(
            select(Session).where(
                Session.user_id == user.id,
                Session.revoked_at.is_(None),
            )
        )
        now = datetime.now(UTC)
        for s in result.scalars().all():
            if current_session_hash and s.session_token_hash == current_session_hash:
                continue  # keep current session
            s.revoked_at = now

        await self._db.flush()
        log_password_changed(str(user.id), ip)

    # ── Email change ──────────────────────────────────────────────────────────

    async def request_email_change(self, user: User, data: ChangeEmailRequest, ip: str) -> str:
        """Re-authenticates, validates new email, returns raw verification token."""
        if not user.is_verified:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "EMAIL_NOT_VERIFIED",
                    "message": "Verify your current email first.",
                },
            )
        if not verify_password(data.current_password, user.password_hash):
            raise HTTPException(
                status_code=400,
                detail={"code": "INVALID_PASSWORD", "message": "Current password is incorrect."},
            )
        new_email = str(data.new_email).lower().strip()
        if await self._users.email_exists(new_email):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "EMAIL_ALREADY_REGISTERED",
                    "message": "That email address is already in use.",
                },
            )
        log_email_change_requested(str(user.id), ip)
        return new_email  # caller (route) creates the token and sends email

    # ── Data export ───────────────────────────────────────────────────────────

    async def export_data(self, user: User) -> dict:  # type: ignore[type-arg]
        """Returns a JSON-serialisable dict of all user data (D-24). Requires re-auth at route."""
        return {
            "exported_at": datetime.now(UTC).isoformat(),
            "profile": {
                "email": user.email,
                "full_name": user.profile.full_name if user.profile else None,
                "preferred_language": user.profile.preferred_language if user.profile else None,
                "timezone": user.profile.timezone if user.profile else None,
                "created_at": user.created_at.isoformat()
                if hasattr(user, "created_at") and user.created_at
                else None,
                "email_verified": user.is_verified,
            },
            "preferences": {
                "theme": user.preferences.theme if user.preferences else "system",
            },
        }

    # ── Account deletion ──────────────────────────────────────────────────────

    async def delete_account(self, user: User, data: DeleteAccountRequest, ip: str) -> None:
        """Re-authenticates, marks deletion_requested, revokes all sessions (D-23)."""
        if not verify_password(data.password, user.password_hash):
            raise HTTPException(
                status_code=400,
                detail={"code": "INVALID_PASSWORD", "message": "Incorrect password."},
            )
        user.status = "deletion_requested"
        await self._sessions.revoke_all_for_user(user.id)
        await self._db.flush()
        log_account_deletion_requested(str(user.id), ip)

        # Synchronous deletion (Phase 1 — no background job yet)
        await self._db.delete(user)
        await self._db.flush()
        logger.info(
            "account_deleted",
            user_id_hash=hashlib.sha256(str(user.id).encode()).hexdigest(),
        )
