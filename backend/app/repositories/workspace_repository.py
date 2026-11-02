import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workspace import Workspace


class WorkspaceRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        name: str,
        workspace_type: str,
        is_default: bool = False,
        description: str | None = None,
    ) -> Workspace:
        workspace = Workspace(
            user_id=user_id,
            name=name,
            workspace_type=workspace_type,
            is_default=is_default,
            description=description,
        )
        self._db.add(workspace)
        await self._db.flush()
        return workspace
