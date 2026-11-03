"""Repository for password-reset and email-verification tokens."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email_verification_token import EmailVerificationToken
from app.models.password_reset_token import PasswordResetToken


class PasswordResetTokenRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(
        self,
        user_id: uuid.UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> PasswordResetToken:
        now = datetime.now(timezone.utc)
        token = PasswordResetToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            created_at=now,
        )
        self._db.add(token)
        await self._db.flush()
        return token

    async def get_valid_by_hash(self, token_hash: str) -> PasswordResetToken | None:
        now = datetime.now(timezone.utc)
        result = await self._db.execute(
            select(PasswordResetToken).where(
                PasswordResetToken.token_hash == token_hash,
                PasswordResetToken.expires_at > now,
                PasswordResetToken.used_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def mark_used(self, token: PasswordResetToken) -> None:
        now = datetime.now(timezone.utc)
        await self._db.execute(
            update(PasswordResetToken)
            .where(PasswordResetToken.id == token.id)
            .values(used_at=now)
        )


class EmailVerificationTokenRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(
        self,
        user_id: uuid.UUID,
        token_hash: str,
        expires_at: datetime,
        purpose: str,
        new_email: str | None = None,
    ) -> EmailVerificationToken:
        now = datetime.now(timezone.utc)
        token = EmailVerificationToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            purpose=purpose,
            new_email=new_email,
            created_at=now,
        )
        self._db.add(token)
        await self._db.flush()
        return token

    async def get_valid_by_hash(
        self, token_hash: str, purpose: str
    ) -> EmailVerificationToken | None:
        now = datetime.now(timezone.utc)
        result = await self._db.execute(
            select(EmailVerificationToken).where(
                EmailVerificationToken.token_hash == token_hash,
                EmailVerificationToken.purpose == purpose,
                EmailVerificationToken.expires_at > now,
                EmailVerificationToken.used_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def mark_used(self, token: EmailVerificationToken) -> None:
        now = datetime.now(timezone.utc)
        await self._db.execute(
            update(EmailVerificationToken)
            .where(EmailVerificationToken.id == token.id)
            .values(used_at=now)
        )
