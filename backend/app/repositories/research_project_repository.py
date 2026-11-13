"""Persistence for research projects (Phase 7 M7.1). Every query is filtered by `user_id`, so an id
that belongs to someone else behaves exactly like a missing one."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Select, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research import ResearchProject

# Allowlisted sort columns (CLAUDE.md rule 4).
SORTS = {
    "updated_at": ResearchProject.updated_at,
    "created_at": ResearchProject.created_at,
    "title": func.lower(ResearchProject.title),
    "target_date": ResearchProject.target_date,
}


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class ResearchProjectRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get(self, user_id: uuid.UUID, project_id: uuid.UUID) -> ResearchProject | None:
        return (
            await self._db.execute(
                select(ResearchProject).where(
                    ResearchProject.user_id == user_id, ResearchProject.id == project_id
                )
            )
        ).scalar_one_or_none()

    def _filtered(
        self,
        stmt: Select[Any],
        user_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID | None,
        status: str | None,
        q: str | None,
        archived: bool,
    ) -> Select[Any]:
        stmt = stmt.where(ResearchProject.user_id == user_id)
        stmt = stmt.where(
            ResearchProject.archived_at.is_not(None)
            if archived
            else ResearchProject.archived_at.is_(None)
        )
        if workspace_id:
            stmt = stmt.where(ResearchProject.workspace_id == workspace_id)
        if status:
            stmt = stmt.where(ResearchProject.status == status)
        if q:
            like = f"%{_escape_like(q.strip())}%"
            stmt = stmt.where(
                or_(
                    ResearchProject.title.ilike(like, escape="\\"),
                    ResearchProject.domain.ilike(like, escape="\\"),
                    ResearchProject.description.ilike(like, escape="\\"),
                )
            )
        return stmt

    async def list_for_user(
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
        total = (
            await self._db.execute(
                self._filtered(
                    select(func.count()).select_from(ResearchProject),
                    user_id,
                    workspace_id=workspace_id,
                    status=status,
                    q=q,
                    archived=archived,
                )
            )
        ).scalar_one()
        column = SORTS[sort_by]
        order = column.desc().nulls_last() if descending else column.asc().nulls_last()
        rows = await self._db.execute(
            self._filtered(
                select(ResearchProject),
                user_id,
                workspace_id=workspace_id,
                status=status,
                q=q,
                archived=archived,
            )
            .order_by(order, ResearchProject.id)
            .limit(limit)
            .offset(offset)
        )
        return list(rows.scalars()), int(total)

    async def add(self, project: ResearchProject) -> ResearchProject:
        self._db.add(project)
        await self._db.flush()
        await self._db.refresh(project)
        return project

    async def delete(self, user_id: uuid.UUID, project_id: uuid.UUID) -> None:
        await self._db.execute(
            delete(ResearchProject).where(
                ResearchProject.user_id == user_id, ResearchProject.id == project_id
            )
        )
