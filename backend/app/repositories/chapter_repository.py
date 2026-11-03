import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chapter import Chapter


class ChapterRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_for_subject(
        self,
        *,
        subject_id: uuid.UUID,
        folder_id: uuid.UUID | None = None,
        folder_filter_set: bool = False,
        include_archived: bool = False,
        q: str | None = None,
        sort_by: str = "display_order",
        sort_dir: str = "asc",
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Chapter], int]:
        stmt = select(Chapter).where(Chapter.subject_id == subject_id)
        count_stmt = select(func.count(Chapter.id)).where(Chapter.subject_id == subject_id)

        if folder_filter_set:
            if folder_id is None:
                stmt = stmt.where(Chapter.folder_id.is_(None))
                count_stmt = count_stmt.where(Chapter.folder_id.is_(None))
            else:
                stmt = stmt.where(Chapter.folder_id == folder_id)
                count_stmt = count_stmt.where(Chapter.folder_id == folder_id)

        if not include_archived:
            stmt = stmt.where(Chapter.archived_at.is_(None))
            count_stmt = count_stmt.where(Chapter.archived_at.is_(None))

        if q:
            pattern = f"%{q.lower()}%"
            stmt = stmt.where(func.lower(Chapter.title).like(pattern))
            count_stmt = count_stmt.where(func.lower(Chapter.title).like(pattern))

        # Allowlist sortable fields
        sort_col = {
            "display_order": Chapter.display_order,
            "title": Chapter.title,
            "updated_at": Chapter.updated_at,
        }.get(sort_by, Chapter.display_order)

        if sort_dir == "desc":
            stmt = stmt.order_by(sort_col.desc())
        else:
            stmt = stmt.order_by(sort_col.asc())

        total = (await self._db.execute(count_stmt)).scalar_one()
        rows = (await self._db.execute(stmt.limit(limit).offset(offset))).scalars().all()
        return list(rows), total

    async def get_for_subject(
        self, *, chapter_id: uuid.UUID, subject_id: uuid.UUID
    ) -> Chapter | None:
        result = await self._db.execute(
            select(Chapter).where(
                Chapter.id == chapter_id,
                Chapter.subject_id == subject_id,
            )
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        subject_id: uuid.UUID,
        title: str,
        folder_id: uuid.UUID | None = None,
        description: str | None = None,
        display_order: int = 0,
        status: str = "not_started",
    ) -> Chapter:
        chapter = Chapter(
            subject_id=subject_id,
            folder_id=folder_id,
            title=title,
            description=description,
            display_order=display_order,
            status=status,
        )
        self._db.add(chapter)
        await self._db.flush()
        return chapter

    async def update(
        self,
        chapter: Chapter,
        *,
        title: str | None = None,
        description: str | None = None,
        folder_id: uuid.UUID | None = None,
        folder_id_set: bool = False,
        display_order: int | None = None,
        status: str | None = None,
    ) -> Chapter:
        if title is not None:
            chapter.title = title
        if description is not None:
            chapter.description = description
        if folder_id_set:
            chapter.folder_id = folder_id
        if display_order is not None:
            chapter.display_order = display_order
        if status is not None:
            chapter.status = status
        await self._db.flush()
        return chapter

    async def bulk_reorder(
        self, *, subject_id: uuid.UUID, chapter_ids: list[uuid.UUID]
    ) -> None:
        """Set display_order 0..N-1 for the given ids in order (D-15)."""
        for idx, cid in enumerate(chapter_ids):
            result = await self._db.execute(
                select(Chapter).where(
                    Chapter.id == cid,
                    Chapter.subject_id == subject_id,
                )
            )
            chapter = result.scalar_one_or_none()
            if chapter is not None:
                chapter.display_order = idx
        await self._db.flush()

    async def archive(self, chapter: Chapter) -> Chapter:
        chapter.archived_at = datetime.now(timezone.utc)
        await self._db.flush()
        return chapter

    async def restore(self, chapter: Chapter) -> Chapter:
        chapter.archived_at = None
        await self._db.flush()
        return chapter

    async def delete(self, chapter: Chapter) -> None:
        await self._db.delete(chapter)
        await self._db.flush()
