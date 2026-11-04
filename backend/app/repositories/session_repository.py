import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session_model import Session


class SessionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        token_hash: str,
        expires_at: datetime,
        user_agent: str | None = None,
        ip_address: str | None = None,
        remember_me: bool = False,
    ) -> Session:
        now = datetime.now(UTC)
        session = Session(
            user_id=user_id,
            session_token_hash=token_hash,
            expires_at=expires_at,
            created_at=now,
            last_used_at=now,
            user_agent=user_agent[:512] if user_agent else None,
            ip_address=ip_address,
            remember_me=remember_me,
        )
        self._db.add(session)
        await self._db.flush()
        return session

    async def get_valid_by_token_hash(self, token_hash: str) -> Session | None:
        now = datetime.now(UTC)
        result = await self._db.execute(
            select(Session).where(
                Session.session_token_hash == token_hash,
                Session.expires_at > now,
                Session.revoked_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def update_last_used(self, session: Session, new_expires_at: datetime) -> None:
        session.last_used_at = datetime.now(UTC)
        session.expires_at = new_expires_at
        await self._db.flush()

    async def revoke(self, session: Session) -> None:
        session.revoked_at = datetime.now(UTC)
        await self._db.flush()

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> None:
        now = datetime.now(UTC)
        result = await self._db.execute(
            select(Session).where(
                Session.user_id == user_id,
                Session.revoked_at.is_(None),
            )
        )
        for s in result.scalars().all():
            s.revoked_at = now
        await self._db.flush()
