"""Dashboard service (Phase 7 M7.11). Everything shown is counted from the owner's own rows; nothing
is estimated or invented, and an empty account returns zeros and an empty activity list."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.research.dashboard_schemas import (
    ResearchDashboardActivity,
    ResearchDashboardCounts,
    ResearchDashboardOut,
)
from app.repositories.research_dashboard_repository import ResearchDashboardRepository
from app.repositories.research_project_repository import ResearchProjectRepository
from app.research.errors import ProjectNotFoundError

RECENT_LIMIT = 10


class ResearchDashboardService:
    def __init__(self, db: AsyncSession) -> None:
        self._repo = ResearchDashboardRepository(db)
        self._projects = ResearchProjectRepository(db)

    async def _build(
        self, user_id: uuid.UUID, workspace_id: uuid.UUID | None, project_id: uuid.UUID | None
    ) -> ResearchDashboardOut:
        counts = await self._repo.counts(user_id, workspace_id, project_id)
        active = None if project_id else await self._repo.active_projects(user_id, workspace_id)
        recent = await self._repo.recent(user_id, workspace_id, project_id, RECENT_LIMIT)
        return ResearchDashboardOut(
            counts=ResearchDashboardCounts(active_projects=active, **counts),
            recent=[
                ResearchDashboardActivity(
                    kind=k, title=t, research_project_id=p, project_title=pt, at=at
                )
                for k, t, p, pt, at in recent
            ],
        )

    async def overview(
        self, user_id: uuid.UUID, workspace_id: uuid.UUID | None
    ) -> ResearchDashboardOut:
        return await self._build(user_id, workspace_id, None)

    async def project(self, user_id: uuid.UUID, project_id: uuid.UUID) -> ResearchDashboardOut:
        if await self._projects.get(user_id, project_id) is None:
            raise ProjectNotFoundError
        return await self._build(user_id, None, project_id)
