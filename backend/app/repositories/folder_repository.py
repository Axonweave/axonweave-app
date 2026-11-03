import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.folder import Folder

_MAX_DEPTH = 3  # D-14


class FolderRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_for_subject(
        self,
        *,
        subject_id: uuid.UUID,
        parent_folder_id: uuid.UUID | None = None,
        include_archived: bool = False,
    ) -> list[Folder]:
        stmt = select(Folder).where(Folder.subject_id == subject_id)
        if parent_folder_id is None:
            stmt = stmt.where(Folder.parent_folder_id.is_(None))
        else:
            stmt = stmt.where(Folder.parent_folder_id == parent_folder_id)
        if not include_archived:
            stmt = stmt.where(Folder.archived_at.is_(None))
        stmt = stmt.order_by(Folder.display_order.asc(), Folder.name.asc())
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_for_subject(
        self, *, folder_id: uuid.UUID, subject_id: uuid.UUID
    ) -> Folder | None:
        result = await self._db.execute(
            select(Folder).where(
                Folder.id == folder_id,
                Folder.subject_id == subject_id,
            )
        )
        return result.scalar_one_or_none()

    async def name_exists(
        self,
        *,
        subject_id: uuid.UUID,
        name: str,
        parent_folder_id: uuid.UUID | None,
        exclude_id: uuid.UUID | None = None,
    ) -> bool:
        """D-11: case-insensitive unique name per parent (null parent = root)."""
        stmt = select(Folder.id).where(
            Folder.subject_id == subject_id,
            func.lower(Folder.name) == name.lower(),
            Folder.archived_at.is_(None),
        )
        if parent_folder_id is None:
            stmt = stmt.where(Folder.parent_folder_id.is_(None))
        else:
            stmt = stmt.where(Folder.parent_folder_id == parent_folder_id)
        if exclude_id is not None:
            stmt = stmt.where(Folder.id != exclude_id)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def get_depth(self, folder_id: uuid.UUID | None) -> int:
        """Return depth of folder_id (1 = root). None returns 0 (used for child-of-root check)."""
        if folder_id is None:
            return 0
        depth = 0
        current_id: uuid.UUID | None = folder_id
        while current_id is not None:
            depth += 1
            result = await self._db.execute(
                select(Folder.parent_folder_id).where(Folder.id == current_id)
            )
            row = result.scalar_one_or_none()
            current_id = row
        return depth

    async def has_children(self, folder_id: uuid.UUID) -> bool:
        """Check if folder has any child folders or chapters (D-12)."""
        from app.models.chapter import Chapter

        child_folder = await self._db.execute(
            select(Folder.id).where(Folder.parent_folder_id == folder_id).limit(1)
        )
        if child_folder.scalar_one_or_none() is not None:
            return True
        child_chapter = await self._db.execute(
            select(Chapter.id).where(Chapter.folder_id == folder_id).limit(1)
        )
        return child_chapter.scalar_one_or_none() is not None

    async def create(
        self,
        *,
        subject_id: uuid.UUID,
        name: str,
        parent_folder_id: uuid.UUID | None = None,
        description: str | None = None,
        display_order: int = 0,
    ) -> Folder:
        folder = Folder(
            subject_id=subject_id,
            name=name,
            parent_folder_id=parent_folder_id,
            description=description,
            display_order=display_order,
        )
        self._db.add(folder)
        await self._db.flush()
        return folder

    async def update(
        self,
        folder: Folder,
        *,
        name: str | None = None,
        description: str | None = None,
        display_order: int | None = None,
    ) -> Folder:
        if name is not None:
            folder.name = name
        if description is not None:
            folder.description = description
        if display_order is not None:
            folder.display_order = display_order
        await self._db.flush()
        return folder

    async def archive(self, folder: Folder) -> Folder:
        folder.archived_at = datetime.now(timezone.utc)
        await self._db.flush()
        return folder

    async def restore(self, folder: Folder) -> Folder:
        folder.archived_at = None
        await self._db.flush()
        return folder

    async def delete(self, folder: Folder) -> None:
        await self._db.delete(folder)
        await self._db.flush()

    @property
    def max_depth(self) -> int:
        return _MAX_DEPTH
