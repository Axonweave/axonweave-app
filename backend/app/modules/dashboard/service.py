"""Dashboard service — real counts and activity scoped to the authenticated user (D-30)."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_log import ActivityLog
from app.models.chapter import Chapter
from app.models.folder import Folder
from app.models.subject import Subject
from app.models.workspace import Workspace
from app.modules.dashboard.schemas import (
    ActivityItem,
    ChapterStatusCounts,
    DashboardStats,
)


class DashboardService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_stats(self, *, user_id: uuid.UUID) -> DashboardStats:
        """All counts are scoped to user via workspace ownership chain."""
        # Workspace count (all, including archived)
        ws_count = (
            await self._db.execute(
                select(func.count(Workspace.id)).where(Workspace.user_id == user_id)
            )
        ).scalar_one()

        # Subject count: join to workspace to scope by user
        subj_count = (
            await self._db.execute(
                select(func.count(Subject.id))
                .join(Workspace, Subject.workspace_id == Workspace.id)
                .where(Workspace.user_id == user_id)
            )
        ).scalar_one()

        # Folder count: join subject → workspace to scope by user
        folder_count = (
            await self._db.execute(
                select(func.count(Folder.id))
                .join(Subject, Folder.subject_id == Subject.id)
                .join(Workspace, Subject.workspace_id == Workspace.id)
                .where(Workspace.user_id == user_id)
            )
        ).scalar_one()

        # Chapter counts by status: join subject → workspace
        status_rows = (
            await self._db.execute(
                select(Chapter.status, func.count(Chapter.id))
                .join(Subject, Chapter.subject_id == Subject.id)
                .join(Workspace, Subject.workspace_id == Workspace.id)
                .where(Workspace.user_id == user_id)
                .group_by(Chapter.status)
            )
        ).all()

        chapter_status: dict[str, int] = {"not_started": 0, "in_progress": 0, "completed": 0}
        total_chapters = 0
        for row_status, row_count in status_rows:
            if row_status in chapter_status:
                chapter_status[row_status] = row_count
            total_chapters += row_count

        return DashboardStats(
            workspace_count=ws_count,
            subject_count=subj_count,
            folder_count=folder_count,
            chapter_count=total_chapters,
            chapter_status=ChapterStatusCounts(**chapter_status),
        )

    async def get_activity(
        self,
        *,
        user_id: uuid.UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[ActivityItem], int]:
        """Recent activity for user, most recent first."""
        base = select(ActivityLog).where(ActivityLog.user_id == user_id)
        count_stmt = select(func.count(ActivityLog.id)).where(ActivityLog.user_id == user_id)

        total = (await self._db.execute(count_stmt)).scalar_one()
        rows = (
            (
                await self._db.execute(
                    base.order_by(ActivityLog.created_at.desc()).limit(limit).offset(offset)
                )
            )
            .scalars()
            .all()
        )

        return [ActivityItem.model_validate(r) for r in rows], total
