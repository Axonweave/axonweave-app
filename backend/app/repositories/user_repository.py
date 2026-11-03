import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.user import User
from app.models.user_preferences import UserPreferences
from app.models.user_profile import UserProfile


class UserRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        result = await self._db.execute(
            select(User)
            .options(selectinload(User.profile), selectinload(User.preferences))
            .where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        """Lookup by normalised (lowercased) email."""
        result = await self._db.execute(
            select(User)
            .options(selectinload(User.profile), selectinload(User.preferences))
            .where(func.lower(User.email) == email.lower().strip())
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        email: str,
        password_hash: str,
        terms_accepted_at: Any,
        terms_version: str,
    ) -> User:
        user = User(
            email=email.lower().strip(),
            password_hash=password_hash,
            status="pending_verification",
            is_verified=False,
            terms_accepted_at=terms_accepted_at,
            terms_version=terms_version,
        )
        self._db.add(user)
        await self._db.flush()  # get the id without committing
        return user

    async def create_profile(self, *, user_id: uuid.UUID, full_name: str) -> UserProfile:
        profile = UserProfile(user_id=user_id, full_name=full_name)
        self._db.add(profile)
        await self._db.flush()
        return profile

    async def create_preferences(self, *, user_id: uuid.UUID) -> UserPreferences:
        prefs = UserPreferences(user_id=user_id)
        self._db.add(prefs)
        await self._db.flush()
        return prefs

    async def email_exists(self, email: str) -> bool:
        result = await self._db.execute(
            select(User.id).where(func.lower(User.email) == email.lower().strip())
        )
        return result.scalar_one_or_none() is not None
