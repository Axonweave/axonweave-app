from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_db as _get_db

# Re-exported for use in route handlers
DbSession = Annotated[AsyncSession, Depends(_get_db)]
