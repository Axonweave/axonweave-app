"""Auth service — register, login, logout, get_me."""

from datetime import datetime, timedelta, timezone

from fastapi import Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.security import (
    generate_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.modules.auth.schemas import TERMS_VERSION, LoginRequest, RegisterRequest
from app.models.user import User
from app.repositories.session_repository import SessionRepository
from app.repositories.user_repository import UserRepository
from app.repositories.workspace_repository import WorkspaceRepository

logger = get_logger(__name__)
settings = get_settings()

# Session lifetimes (D-19)
_SESSION_IDLE_DAYS = 7
_SESSION_REMEMBER_IDLE_DAYS = 30
_SESSION_ABSOLUTE_MAX_DAYS = 30


def _idle_delta(remember_me: bool) -> timedelta:
    return timedelta(days=_SESSION_REMEMBER_IDLE_DAYS if remember_me else _SESSION_IDLE_DAYS)


def _set_session_cookies(response: Response, raw_token: str, csrf_token: str, expires_at: datetime) -> None:
    """Set the aw_session (HTTP-only) and csrf_token (readable by JS) cookies."""
    max_age = int((expires_at - datetime.now(timezone.utc)).total_seconds())
    response.set_cookie(
        key=settings.cookie_name,
        value=raw_token,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite.value,
        path="/",
    )
    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        max_age=max_age,
        httponly=False,  # JS must read this
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite.value,
        path="/",
    )


def _clear_session_cookies(response: Response) -> None:
    response.delete_cookie(key=settings.cookie_name, path="/")
    response.delete_cookie(key="csrf_token", path="/")


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._users = UserRepository(db)
        self._sessions = SessionRepository(db)
        self._workspaces = WorkspaceRepository(db)

    async def register(self, data: RegisterRequest, response: Response) -> User:
        """Create user + profile + preferences + default workspace in one transaction (D-13)."""
        if await self._users.email_exists(data.email):
            from fastapi import HTTPException
            raise HTTPException(
                status_code=409,
                detail={"code": "EMAIL_ALREADY_REGISTERED", "message": "An account with this email already exists."},
            )

        now = datetime.now(timezone.utc)
        pw_hash = hash_password(data.password)

        user = await self._users.create(
            email=data.email,
            password_hash=pw_hash,
            terms_accepted_at=now,
            terms_version=TERMS_VERSION,
        )
        await self._users.create_profile(user_id=user.id, full_name=data.full_name)
        await self._users.create_preferences(user_id=user.id)
        await self._workspaces.create(
            user_id=user.id,
            name="Personal",
            workspace_type="personal_learning",
            is_default=True,
            description="Your default personal workspace.",
        )

        # Re-fetch with eager-loaded relationships so UserOut serialisation works
        loaded_user = await self._users.get_by_id(user.id)
        assert loaded_user is not None
        logger.info("user_registered", user_id=str(user.id))
        return loaded_user

    async def login(self, data: LoginRequest, request: Request, response: Response) -> User:
        """Authenticate, create session, set cookies. Generic error if credentials wrong."""
        from fastapi import HTTPException

        _generic_err = HTTPException(
            status_code=401,
            detail={"code": "INVALID_CREDENTIALS", "message": "Invalid email or password."},
        )

        user = await self._users.get_by_email(data.email)
        if user is None:
            logger.info("login_unknown_email")
            raise _generic_err

        if not verify_password(data.password, user.password_hash):
            logger.info("login_bad_password", user_id=str(user.id))
            raise _generic_err

        if user.status in ("suspended", "deactivated", "deletion_requested"):
            logger.info("login_inactive_account", user_id=str(user.id), status=user.status)
            raise HTTPException(
                status_code=403,
                detail={"code": "ACCOUNT_INACTIVE", "message": "This account is not active."},
            )

        now = datetime.now(timezone.utc)
        expires_at = now + _idle_delta(data.remember_me)
        # Clamp to absolute max (D-19)
        absolute_max = now + timedelta(days=_SESSION_ABSOLUTE_MAX_DAYS)
        if expires_at > absolute_max:
            expires_at = absolute_max

        raw_token = generate_token()
        token_hash = hash_token(raw_token)
        csrf_token = generate_token()

        user_agent = request.headers.get("user-agent")
        ip_address = request.client.host if request.client else None

        await self._sessions.create(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
            user_agent=user_agent,
            ip_address=ip_address,
            remember_me=data.remember_me,
        )

        _set_session_cookies(response, raw_token, csrf_token, expires_at)
        logger.info("user_logged_in", user_id=str(user.id))
        return user

    async def logout(self, raw_token: str, response: Response) -> None:
        """Revoke session and expire cookies."""
        token_hash = hash_token(raw_token)
        session = await self._sessions.get_valid_by_token_hash(token_hash)
        if session:
            await self._sessions.revoke(session)
            logger.info("user_logged_out", user_id=str(session.user_id))
        _clear_session_cookies(response)

    async def get_current_session_user(self, raw_token: str) -> User | None:
        """
        Validate session token, slide expiry, return user.
        Returns None if session is missing/expired/revoked.
        """
        token_hash = hash_token(raw_token)
        session = await self._sessions.get_valid_by_token_hash(token_hash)
        if session is None:
            return None

        # Slide expiry (D-19)
        now = datetime.now(timezone.utc)
        new_expires = now + _idle_delta(session.remember_me)
        absolute_max = session.created_at + timedelta(days=_SESSION_ABSOLUTE_MAX_DAYS)
        if new_expires > absolute_max:
            new_expires = absolute_max
        await self._sessions.update_last_used(session, new_expires)

        return await self._users.get_by_id(session.user_id)
