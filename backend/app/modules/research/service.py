"""Research project service (Phase 7 M7.1). Ownership is resolved here: a workspace or project that
is not the caller's is a 404, the same as a missing one (CLAUDE.md rules 1 to 3)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research import ResearchProject
from app.modules.research.schemas import ProjectCreate, ProjectPatch
from app.repositories.research_project_repository import ResearchProjectRepository
from app.repositories.workspace_repository import WorkspaceRepository
from app.research.errors import (
    InvalidProjectDatesError,
    ProjectArchivedError,
    ProjectNotArchivedError,
    ProjectNotFoundError,
    WorkspaceNotFoundError,
)


class ResearchProjectService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._repo = ResearchProjectRepository(db)

    async def _owned(self, user_id: uuid.UUID, project_id: uuid.UUID) -> ResearchProject:
        project = await self._repo.get(user_id, project_id)
        if project is None:
            raise ProjectNotFoundError()
        return project

    async def create(self, user_id: uuid.UUID, body: ProjectCreate) -> ResearchProject:
        if await WorkspaceRepository(self._db).get_for_user(body.workspace_id, user_id) is None:
            raise WorkspaceNotFoundError()
        project = await self._repo.add(ResearchProject(user_id=user_id, **body.model_dump()))
        await self._db.commit()
        return project

    async def get(self, user_id: uuid.UUID, project_id: uuid.UUID) -> ResearchProject:
        return await self._owned(user_id, project_id)

    async def list(
        self,
        user_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID | None,
        status: str | None,
        q: str | None,
        archived: bool,
        sort_by: str,
        descending: bool,
        limit: int,
        offset: int,
    ) -> tuple[list[ResearchProject], int]:
        if workspace_id is not None and (
            await WorkspaceRepository(self._db).get_for_user(workspace_id, user_id) is None
        ):
            raise WorkspaceNotFoundError()
        return await self._repo.list_for_user(
            user_id,
            workspace_id=workspace_id,
            status=status,
            q=q,
            archived=archived,
            sort_by=sort_by,
            descending=descending,
            limit=limit,
            offset=offset,
        )

    async def update(
        self, user_id: uuid.UUID, project_id: uuid.UUID, body: ProjectPatch
    ) -> ResearchProject:
        project = await self._owned(user_id, project_id)
        if project.archived_at is not None:
            raise ProjectArchivedError()
        changes: dict[str, Any] = body.model_dump(exclude_unset=True)
        # A required field cannot be cleared with null.
        for required in ("title", "status", "objectives", "research_questions", "keywords"):
            if required in changes and changes[required] is None:
                del changes[required]
        start = changes.get("start_date", project.start_date)
        target = changes.get("target_date", project.target_date)
        if start and target and target < start:
            raise InvalidProjectDatesError()
        for key, value in changes.items():
            setattr(project, key, value)
        await self._db.commit()
        await self._db.refresh(project)
        return project

    async def archive(self, user_id: uuid.UUID, project_id: uuid.UUID) -> ResearchProject:
        project = await self._owned(user_id, project_id)
        if project.archived_at is None:
            project.archived_at = datetime.now(UTC)
            await self._db.commit()
            await self._db.refresh(project)
        return project

    async def restore(self, user_id: uuid.UUID, project_id: uuid.UUID) -> ResearchProject:
        project = await self._owned(user_id, project_id)
        if project.archived_at is None:
            raise ProjectNotArchivedError()
        project.archived_at = None
        await self._db.commit()
        await self._db.refresh(project)
        return project

    async def delete(self, user_id: uuid.UUID, project_id: uuid.UUID) -> None:
        """Permanent. Later milestones attach papers, notes and drafts that are removed with it."""
        await self._owned(user_id, project_id)
        await self._repo.delete(user_id, project_id)
        await self._db.commit()
