"""Read-only aggregate queries for the Research Studio dashboard (Phase 7 M7.11). Every query is
filtered by `user_id`, and counts only cover projects that are not archived unless one project is
asked for explicitly."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research import (
    ResearchComparison,
    ResearchContradiction,
    ResearchDraft,
    ResearchEvidenceMatrix,
    ResearchGap,
    ResearchPaper,
    ResearchProject,
)

AWAITING = ("not_analysed", "queued", "analysing")
IN_PROGRESS = ("draft", "in_review")


class ResearchDashboardRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    @staticmethod
    def _scope(
        stmt: Select[Any],
        model: Any,
        user_id: uuid.UUID,
        workspace_id: uuid.UUID | None,
        project_id: uuid.UUID | None,
    ) -> Select[Any]:
        """Restrict `model` rows to the owner's projects: one project, or the active ones."""
        stmt = stmt.join(
            ResearchProject,
            (ResearchProject.id == model.research_project_id)
            & (ResearchProject.user_id == model.user_id),
        ).where(model.user_id == user_id)
        if project_id:
            return stmt.where(model.research_project_id == project_id)
        stmt = stmt.where(ResearchProject.archived_at.is_(None))
        if workspace_id:
            stmt = stmt.where(ResearchProject.workspace_id == workspace_id)
        return stmt

    async def _count(
        self,
        model: Any,
        user_id: uuid.UUID,
        workspace_id: uuid.UUID | None,
        project_id: uuid.UUID | None,
        *where: Any,
    ) -> int:
        stmt = self._scope(select(func.count(model.id)), model, user_id, workspace_id, project_id)
        for clause in where:
            stmt = stmt.where(clause)
        return int((await self._db.execute(stmt)).scalar_one())

    async def active_projects(self, user_id: uuid.UUID, workspace_id: uuid.UUID | None) -> int:
        stmt = select(func.count(ResearchProject.id)).where(
            ResearchProject.user_id == user_id, ResearchProject.archived_at.is_(None)
        )
        if workspace_id:
            stmt = stmt.where(ResearchProject.workspace_id == workspace_id)
        return int((await self._db.execute(stmt)).scalar_one())

    async def counts(
        self, user_id: uuid.UUID, workspace_id: uuid.UUID | None, project_id: uuid.UUID | None
    ) -> dict[str, int]:
        args = (user_id, workspace_id, project_id)
        live = ResearchPaper.archived_at.is_(None)
        return {
            "papers": await self._count(ResearchPaper, *args, live),
            "papers_analysed": await self._count(
                ResearchPaper, *args, live, ResearchPaper.analysis_status == "analysed"
            ),
            "papers_awaiting": await self._count(
                ResearchPaper, *args, live, ResearchPaper.analysis_status.in_(AWAITING)
            ),
            "papers_failed": await self._count(
                ResearchPaper, *args, live, ResearchPaper.analysis_status == "failed"
            ),
            "comparisons": await self._count(ResearchComparison, *args),
            "matrices": await self._count(ResearchEvidenceMatrix, *args),
            "candidate_gaps": await self._count(
                ResearchGap, *args, ResearchGap.validation_status == "suggested"
            ),
            "contradictions_to_review": await self._count(
                ResearchContradiction, *args, ResearchContradiction.review_status == "unreviewed"
            ),
            "drafts_in_progress": await self._count(
                ResearchDraft, *args, ResearchDraft.status.in_(IN_PROGRESS)
            ),
        }

    async def recent(
        self,
        user_id: uuid.UUID,
        workspace_id: uuid.UUID | None,
        project_id: uuid.UUID | None,
        limit: int,
    ) -> list[tuple[str, str, uuid.UUID, str, datetime]]:
        """Latest changes as (kind, title, project id, project title, time), newest first."""
        sources: list[tuple[str, Any, Any]] = [
            ("paper_added", ResearchPaper, ResearchPaper.created_at),
            ("comparison_saved", ResearchComparison, ResearchComparison.updated_at),
            ("matrix_updated", ResearchEvidenceMatrix, ResearchEvidenceMatrix.updated_at),
            ("draft_updated", ResearchDraft, ResearchDraft.updated_at),
        ]
        rows: list[tuple[str, str, uuid.UUID, str, datetime]] = []
        for kind, model, when in sources:
            stmt = self._scope(
                select(model.title, model.research_project_id, ResearchProject.title, when),
                model,
                user_id,
                workspace_id,
                project_id,
            )
            if model is ResearchPaper:
                stmt = stmt.where(ResearchPaper.archived_at.is_(None))
            stmt = stmt.order_by(when.desc()).limit(limit)
            for title, pid, ptitle, at in (await self._db.execute(stmt)).all():
                rows.append((kind, title, pid, ptitle, at))
        rows.sort(key=lambda r: r[4], reverse=True)
        return rows[:limit]
