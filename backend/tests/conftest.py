import os
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.security import generate_token, hash_password, hash_token
from app.database.base import Base
from app.main import app
from app.models.session_model import Session
from app.models.user import User
from app.models.user_preferences import UserPreferences
from app.models.user_profile import UserProfile
from app.models.workspace import Workspace

_test_url = os.environ.get(
    "DATABASE_TEST_URL",
    os.environ.get(
        "DATABASE_MIGRATION_URL",
        "postgresql+psycopg://axonweave_owner:axonweave_owner_dev_password@localhost:5432/axonweave_test",
    ),
)

_test_engine = create_async_engine(_test_url, echo=False, pool_pre_ping=True)
_TestSessionLocal = async_sessionmaker(
    bind=_test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def create_test_tables() -> AsyncGenerator[None, None]:
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with _TestSessionLocal() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(
        transport=ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="http://test",
    ) as ac:
        yield ac


async def _make_user(db: AsyncSession, *, email: str, full_name: str = "Test User") -> User:
    """Create a verified active user directly in the DB."""
    user = User(
        email=email.lower(),
        password_hash=hash_password("TestPassword123!"),
        status="active",
        is_verified=True,
        email_verified_at=datetime.now(timezone.utc),
        terms_accepted_at=datetime.now(timezone.utc),
        terms_version="1.0",
    )
    db.add(user)
    await db.flush()

    db.add(UserProfile(user_id=user.id, full_name=full_name))
    db.add(UserPreferences(user_id=user.id))
    db.add(Workspace(user_id=user.id, name="Personal", workspace_type="personal_learning", is_default=True))
    await db.flush()
    return user


async def _make_session(db: AsyncSession, user: User) -> tuple[str, str]:
    """
    Create a valid session for user. Returns (raw_token, csrf_token).
    The raw_token should be used as the aw_session cookie value.
    """
    raw_token = generate_token()
    csrf_token = generate_token()
    now = datetime.now(timezone.utc)
    session = Session(
        user_id=user.id,
        session_token_hash=hash_token(raw_token),
        expires_at=now + timedelta(days=7),
        created_at=now,
        last_used_at=now,
    )
    db.add(session)
    await db.flush()
    return raw_token, csrf_token


@pytest_asyncio.fixture
async def create_user_and_session(
    db_session: AsyncSession,
) -> AsyncGenerator[tuple[User, str, str], None]:
    """
    Fixture that provides (user, raw_session_token, csrf_token).
    Use raw_session_token as the aw_session cookie and csrf_token as X-CSRF-Token header.
    """
    user = await _make_user(db_session, email="fixture@example.com")
    raw_token, csrf_token = await _make_session(db_session, user)
    await db_session.commit()
    yield user, raw_token, csrf_token
