"""Activity log writes (D-08). Stores only the entity name snapshot, never content."""

import uuid
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_log import ActivityLog

ActivityAction = Literal["created", "updated", "archived", "restored", "deleted"]
ActivityEntity = Literal["workspace", "subject", "folder", "chapter"]


class ActivityRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def record(
        self,
        *,
        user_id: uuid.UUID,
        action: ActivityAction,
        entity_type: ActivityEntity,
        entity_id: uuid.UUID,
        entity_name: str,
        workspace_id: uuid.UUID | None,
    ) -> None:
        """Add one activity row in the caller's transaction (caller commits)."""
        self._db.add(
            ActivityLog(
                user_id=user_id,
                workspace_id=workspace_id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                entity_name=entity_name[:255],
                created_at=datetime.now(UTC),
            )
        )
        await self._db.flush()
