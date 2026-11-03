import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.subject import Subject


class SubjectRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_for_workspace(
        self, *, subject_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> Subject | None:
        """Fetch subject scoped to workspace — returns None (→ 404) if not found or wrong workspace."""
        result = await self._db.execute(
            select(Subject).where(
                Subject.id == subject_id,
                Subject.workspace_id == workspace_id,
            )
        )
        return result.scalar_one_or_none()
