import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.subject import Subject


class SubjectRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_for_workspace(
        self,
        *,
        workspace_id: uuid.UUID,
        include_archived: bool = False,
        q: str | None = None,
        sort_by: str = "name",
        sort_dir: str = "asc",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Subject], int]:
        """List subjects in a workspace with optional search/filter/sort (D-28)."""
        stmt = select(Subject).where(Subject.workspace_id == workspace_id)
        count_stmt = select(func.count(Subject.id)).where(Subject.workspace_id == workspace_id)

        if not include_archived:
            stmt = stmt.where(Subject.archived_at.is_(None))
            count_stmt = count_stmt.where(Subject.archived_at.is_(None))

        if q:
            pattern = f"%{q.lower()}%"
            stmt = stmt.where(func.lower(Subject.name).like(pattern))
            count_stmt = count_stmt.where(func.lower(Subject.name).like(pattern))

        # Allowlist sortable fields (D-28)
        sort_col = Subject.name if sort_by == "name" else Subject.updated_at
        if sort_dir == "desc":
            stmt = stmt.order_by(sort_col.desc())
        else:
            stmt = stmt.order_by(sort_col.asc())

        total = (await self._db.execute(count_stmt)).scalar_one()
        rows = (await self._db.execute(stmt.limit(limit).offset(offset))).scalars().all()
        return list(rows), total

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

    async def name_exists(
        self,
        *,
        workspace_id: uuid.UUID,
        name: str,
        exclude_id: uuid.UUID | None = None,
    ) -> bool:
        """Case-insensitive uniqueness check among non-archived subjects (D-11)."""
        stmt = select(Subject.id).where(
            Subject.workspace_id == workspace_id,
            func.lower(Subject.name) == name.lower(),
            Subject.archived_at.is_(None),
        )
        if exclude_id is not None:
            stmt = stmt.where(Subject.id != exclude_id)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def create(
        self,
        *,
        workspace_id: uuid.UUID,
        name: str,
        description: str | None = None,
        colour: str | None = None,
        icon: str | None = None,
    ) -> Subject:
        subject = Subject(
            workspace_id=workspace_id,
            name=name,
            description=description,
            colour=colour,
            icon=icon,
        )
        self._db.add(subject)
        await self._db.flush()
        return subject

    async def update(
        self,
        subject: Subject,
        *,
        name: str | None = None,
        description: str | None = None,
        colour: str | None = None,
        icon: str | None = None,
    ) -> Subject:
        if name is not None:
            subject.name = name
        if description is not None:
            subject.description = description
        if colour is not None:
            subject.colour = colour
        if icon is not None:
            subject.icon = icon
        await self._db.flush()
        return subject

    async def archive(self, subject: Subject) -> Subject:
        subject.archived_at = datetime.now(timezone.utc)
        await self._db.flush()
        return subject

    async def restore(self, subject: Subject) -> Subject:
        subject.archived_at = None
        await self._db.flush()
        return subject

    async def delete(self, subject: Subject) -> None:
        await self._db.delete(subject)
        await self._db.flush()
