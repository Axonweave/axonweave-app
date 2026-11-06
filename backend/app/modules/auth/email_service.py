"""Email-verification and password-reset service (A3)."""

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.email import EmailSender
from app.core.email_templates import (
    email_change_email,
    password_reset_email,
    verification_email,
)
from app.core.logging import get_logger
from app.core.security import generate_token, hash_password, hash_token
from app.core.security_logging import (
    log_email_verified,
    log_password_reset_completed,
    log_password_reset_requested,
    log_verification_email_sent,
)
from app.models.user import User
from app.repositories.session_repository import SessionRepository
from app.repositories.token_repository import (
    EmailVerificationTokenRepository,
    PasswordResetTokenRepository,
)
from app.repositories.user_repository import UserRepository

logger = get_logger(__name__)
settings = get_settings()

_RESET_TOKEN_TTL = timedelta(minutes=30)  # D-20
_VERIFY_TOKEN_TTL = timedelta(hours=24)  # D-20


class EmailAuthService:
    def __init__(self, db: AsyncSession, sender: EmailSender) -> None:
        self._db = db
        self.__sender = sender
        self._users = UserRepository(db)
        self._sessions = SessionRepository(db)
        self._reset_tokens = PasswordResetTokenRepository(db)
        self._verify_tokens = EmailVerificationTokenRepository(db)

    # ── Email verification ──────────────────────────────────────────────────

    async def send_verification_email(self, user: User) -> None:
        """Generate a verify_email token and send the link."""
        raw = generate_token()
        token_hash = hash_token(raw)
        expires_at = datetime.now(UTC) + _VERIFY_TOKEN_TTL

        await self._verify_tokens.create(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
            purpose="verify_email",
        )

        full_name = user.profile.full_name if user.profile else "there"
        verify_url = f"{settings.frontend_url}/verify-email?token={raw}"
        html, text = verification_email(full_name, verify_url)
        await self._sender.send(user.email, "Verify your Axonweave email", html, text)
        log_verification_email_sent(str(user.id))

    async def send_email_change_email(self, user: User, new_email: str) -> None:
        """Create a change_email token bound to new_email and send the link to the NEW address."""
        raw = generate_token()
        await self._verify_tokens.create(
            user_id=user.id,
            token_hash=hash_token(raw),
            expires_at=datetime.now(UTC) + _VERIFY_TOKEN_TTL,
            purpose="change_email",
            new_email=new_email,
        )
        full_name = user.profile.full_name if user.profile else "there"
        verify_url = f"{settings.frontend_url}/verify-email?token={raw}"
        html, text = email_change_email(full_name, verify_url)
        await self._sender.send(new_email, "Confirm your new Axonweave email", html, text)
        log_verification_email_sent(str(user.id))

    async def verify_email(self, raw_token: str, ip: str) -> None:
        """Mark account as verified, or apply a pending email change. 400 on bad/expired token."""
        token_hash = hash_token(raw_token)
        token = await self._verify_tokens.get_valid_by_hash(token_hash, "verify_email")
        change_token = None
        if token is None:
            change_token = await self._verify_tokens.get_valid_by_hash(token_hash, "change_email")
            token = change_token
        if token is None:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "INVALID_TOKEN",
                    "message": "Verification link is invalid or has expired.",
                },
            )

        user = await self._users.get_by_id(token.user_id)
        if user is None:
            raise HTTPException(
                status_code=400, detail={"code": "INVALID_TOKEN", "message": "Invalid token."}
            )

        now = datetime.now(UTC)
        if change_token is not None:
            new_email = (change_token.new_email or "").lower()
            if not new_email or await self._users.email_exists(new_email):
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "EMAIL_ALREADY_REGISTERED",
                        "message": "That email address is already in use.",
                    },
                )
            user.email = new_email
        user.email_verified_at = now
        user.is_verified = True
        user.status = "active"
        await self._verify_tokens.mark_used(token)
        await self._db.flush()
        log_email_verified(str(user.id), ip)

    async def resend_verification(self, user: User) -> None:
        """Re-send verification email (rate-limited at route level)."""
        if user.is_verified:
            raise HTTPException(
                status_code=409,
                detail={"code": "ALREADY_VERIFIED", "message": "Email is already verified."},
            )
        await self.send_verification_email(user)

    # ── Password reset ──────────────────────────────────────────────────────

    async def forgot_password(self, email: str, ip: str) -> None:
        """
        Always return success — never reveal whether the email exists (D spec 5.5).
        Only sends email if account exists.
        """
        log_password_reset_requested(ip)
        user = await self._users.get_by_email(email)
        if user is None:
            return  # Silent — do not leak existence

        raw = generate_token()
        token_hash = hash_token(raw)
        expires_at = datetime.now(UTC) + _RESET_TOKEN_TTL

        await self._reset_tokens.create(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
        )

        full_name = user.profile.full_name if user.profile else "there"
        reset_url = f"{settings.frontend_url}/reset-password?token={raw}"
        html, text = password_reset_email(full_name, reset_url)
        await self._sender.send(user.email, "Reset your Axonweave password", html, text)

    async def reset_password(self, raw_token: str, new_password: str, ip: str) -> None:
        """Validate reset token, hash + set new password, revoke all sessions."""
        token_hash = hash_token(raw_token)
        token = await self._reset_tokens.get_valid_by_hash(token_hash)
        if token is None:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "INVALID_TOKEN",
                    "message": "Reset link is invalid or has expired.",
                },
            )

        user = await self._users.get_by_id(token.user_id)
        if user is None:
            raise HTTPException(
                status_code=400, detail={"code": "INVALID_TOKEN", "message": "Invalid token."}
            )

        user.password_hash = hash_password(new_password)
        await self._reset_tokens.mark_used(token)
        await self._sessions.revoke_all_for_user(user.id)
        await self._db.flush()
        log_password_reset_completed(str(user.id), ip)

    @property
    def _sender(self) -> EmailSender:
        return self.__sender
