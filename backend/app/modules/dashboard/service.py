"""Dashboard service — real counts and activity scoped to the authenticated user (D-30)."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.dashboard.schemas import (
    ActivityItem,
    ArchivedItem,
    ChapterStatusCounts,
    DashboardStats,
    RecentSubjectItem,
    WorkspaceOverviewItem,
)
from app.repositories.dashboard_repository import DashboardRepository


class DashboardService:
    def __init__(self, db: AsyncSession) -> None:
        self._repo = DashboardRepository(db)

    async def get_stats(self, *, user_id: uuid.UUID) -> DashboardStats:
        """All counts are scoped to user via workspace ownership chain."""
        status_counts = await self._repo.chapter_status_counts(user_id)
        known = {key: status_counts.get(key, 0) for key in ChapterStatusCounts.model_fields}
        return DashboardStats(
            workspace_count=await self._repo.count_workspaces(user_id),
            subject_count=await self._repo.count_subjects(user_id),
            folder_count=await self._repo.count_folders(user_id),
            chapter_count=sum(status_counts.values()),
            chapter_status=ChapterStatusCounts(**known),
        )

    async def get_activity(
        self, *, user_id: uuid.UUID, limit: int = 20, offset: int = 0
    ) -> tuple[list[ActivityItem], int]:
        """Recent activity for user, most recent first, with each entity's current state."""
        rows, total = await self._repo.list_activity(user_id, limit=limit, offset=offset)
        states = await self._repo.entity_states(
            user_id,
            [(r.entity_type, r.entity_id) for r in rows if r.entity_id is not None],
        )
        items = []
        for row in rows:
            item = ActivityItem.model_validate(row)
            if row.entity_id is not None:
                state = states.get((row.entity_type, row.entity_id))
                if state == "active" or state == "archived":
                    item.entity_status = state
            items.append(item)
        return items, total

    async def get_workspace_overview(
        self, *, user_id: uuid.UUID, limit: int
    ) -> tuple[list[WorkspaceOverviewItem], int]:
        rows, total = await self._repo.workspace_overview(user_id, limit=limit)
        return [
            WorkspaceOverviewItem(
                id=r.workspace.id,
                name=r.workspace.name,
                description=r.workspace.description,
                is_default=r.workspace.is_default,
                subject_count=r.subject_count,
                updated_at=r.workspace.updated_at,
            )
            for r in rows
        ], total

    async def get_recent_subjects(
        self, *, user_id: uuid.UUID, limit: int
    ) -> list[RecentSubjectItem]:
        rows = await self._repo.recent_subjects(user_id, limit=limit)
        return [
            RecentSubjectItem(
                id=r.subject.id,
                name=r.subject.name,
                workspace_id=r.subject.workspace_id,
                workspace_name=r.workspace_name,
                updated_at=r.subject.updated_at,
            )
            for r in rows
        ]

    async def get_archived(
        self, *, user_id: uuid.UUID, limit: int, offset: int
    ) -> tuple[list[ArchivedItem], int]:
        rows, total = await self._repo.list_archived(user_id, limit=limit, offset=offset)
        return [
            ArchivedItem(
                type=r.item_type,  # type: ignore[arg-type]
                id=r.id,
                name=r.name,
                archived_at=r.archived_at,
                workspace_id=r.workspace_id,
                workspace_name=r.workspace_name,
                subject_id=r.subject_id,
                subject_name=r.subject_name,
            )
            for r in rows
        ], total
