"""Database sessions for Celery tasks.

Each task runs its async work with `asyncio.run`, which creates a fresh event loop. A pooled async
engine is bound to one loop, so tasks use a short-lived NullPool engine instead of the API's pool.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings


@asynccontextmanager
async def task_session_factory(
    url: str | None = None,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(url or str(get_settings().database_url), poolclass=NullPool)
    try:
        yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    finally:
        await engine.dispose()
