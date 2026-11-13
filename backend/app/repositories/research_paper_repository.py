"""Persistence for research papers (Phase 7 M7.2). Every query is filtered by `user_id`."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Select, Text, cast, delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.research import ResearchPaper, ResearchPaperDuplicateReview

MAX_PAPERS_FOR_DUPLICATES = 2000

SORTS = {
    "updated_at": ResearchPaper.updated_at,
    "created_at": ResearchPaper.created_at,
    "title": func.lower(ResearchPaper.title),
    "publication_year": ResearchPaper.publication_year,
}

Row = tuple[ResearchPaper, str | None, str | None]


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class ResearchPaperRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    def _with_document(self) -> Select[Any]:
        return select(ResearchPaper, Document.display_name, Document.processing_status).outerjoin(
            Document,
            (Document.id == ResearchPaper.document_id)
            & (Document.user_id == ResearchPaper.user_id),
        )

    async def get(self, user_id: uuid.UUID, paper_id: uuid.UUID) -> Row | None:
        row = (
            await self._db.execute(
                self._with_document().where(
                    ResearchPaper.user_id == user_id, ResearchPaper.id == paper_id
                )
            )
        ).first()
        return None if row is None else (row[0], row[1], row[2])

    async def get_many(
        self, user_id: uuid.UUID, project_id: uuid.UUID, ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, ResearchPaper]:
        rows = await self._db.execute(
            select(ResearchPaper).where(
                ResearchPaper.user_id == user_id,
                ResearchPaper.research_project_id == project_id,
                ResearchPaper.id.in_(ids),
            )
        )
        return {p.id: p for p in rows.scalars()}

    def _filtered(
        self,
        stmt: Select[Any],
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        *,
        q: str | None,
        status: str | None,
        year: int | None,
        has_file: bool | None,
        archived: bool,
    ) -> Select[Any]:
        stmt = stmt.where(
            ResearchPaper.user_id == user_id, ResearchPaper.research_project_id == project_id
        )
        stmt = stmt.where(
            ResearchPaper.archived_at.is_not(None)
            if archived
            else ResearchPaper.archived_at.is_(None)
        )
        if status:
            stmt = stmt.where(ResearchPaper.status == status)
        if year:
            stmt = stmt.where(ResearchPaper.publication_year == year)
        if has_file is not None:
            stmt = stmt.where(
                ResearchPaper.document_id.is_not(None)
                if has_file
                else ResearchPaper.document_id.is_(None)
            )
        if q:
            like = f"%{_escape_like(q.strip())}%"
            stmt = stmt.where(
                or_(
                    ResearchPaper.title.ilike(like, escape="\\"),
                    ResearchPaper.venue.ilike(like, escape="\\"),
                    ResearchPaper.doi.ilike(like, escape="\\"),
                    cast(ResearchPaper.authors, Text).ilike(like, escape="\\"),
                )
            )
        return stmt

    async def list_for_project(
        self,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        *,
        q: str | None,
        status: str | None,
        year: int | None,
        has_file: bool | None,
        archived: bool,
        sort_by: str,
        descending: bool,
        limit: int,
        offset: int,
    ) -> tuple[list[Row], int]:
        total = (
            await self._db.execute(
                self._filtered(
                    select(func.count()).select_from(ResearchPaper),
                    user_id,
                    project_id,
                    q=q,
                    status=status,
                    year=year,
                    has_file=has_file,
                    archived=archived,
                )
            )
        ).scalar_one()
        column = SORTS[sort_by]
        order = column.desc().nulls_last() if descending else column.asc().nulls_last()
        rows = await self._db.execute(
            self._filtered(
                self._with_document(),
                user_id,
                project_id,
                q=q,
                status=status,
                year=year,
                has_file=has_file,
                archived=archived,
            )
            .order_by(order, ResearchPaper.id)
            .limit(limit)
            .offset(offset)
        )
        return [(r[0], r[1], r[2]) for r in rows.all()], int(total)

    async def all_for_duplicates(
        self, user_id: uuid.UUID, project_id: uuid.UUID
    ) -> list[ResearchPaper]:
        rows = await self._db.execute(
            select(ResearchPaper)
            .where(
                ResearchPaper.user_id == user_id,
                ResearchPaper.research_project_id == project_id,
                ResearchPaper.archived_at.is_(None),
            )
            .order_by(ResearchPaper.id)
            .limit(MAX_PAPERS_FOR_DUPLICATES)
        )
        return list(rows.scalars())

    async def doi_taken(
        self,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        doi: str,
        *,
        except_id: uuid.UUID | None = None,
    ) -> bool:
        stmt = select(ResearchPaper.id).where(
            ResearchPaper.user_id == user_id,
            ResearchPaper.research_project_id == project_id,
            ResearchPaper.doi == doi,
        )
        if except_id:
            stmt = stmt.where(ResearchPaper.id != except_id)
        return (await self._db.execute(stmt.limit(1))).first() is not None

    async def document_linked(
        self,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        document_id: uuid.UUID,
        *,
        except_id: uuid.UUID | None = None,
    ) -> bool:
        stmt = select(ResearchPaper.id).where(
            ResearchPaper.user_id == user_id,
            ResearchPaper.research_project_id == project_id,
            ResearchPaper.document_id == document_id,
        )
        if except_id:
            stmt = stmt.where(ResearchPaper.id != except_id)
        return (await self._db.execute(stmt.limit(1))).first() is not None

    async def add(self, paper: ResearchPaper) -> ResearchPaper:
        self._db.add(paper)
        await self._db.flush()
        return paper

    async def delete(self, user_id: uuid.UUID, paper_id: uuid.UUID) -> None:
        await self._db.execute(
            delete(ResearchPaper).where(
                ResearchPaper.user_id == user_id, ResearchPaper.id == paper_id
            )
        )

    async def counts_by_project(
        self, user_id: uuid.UUID, project_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, int]:
        if not project_ids:
            return {}
        rows = await self._db.execute(
            select(ResearchPaper.research_project_id, func.count())
            .where(
                ResearchPaper.user_id == user_id,
                ResearchPaper.research_project_id.in_(project_ids),
                ResearchPaper.archived_at.is_(None),
            )
            .group_by(ResearchPaper.research_project_id)
        )
        return {pid: int(n) for pid, n in rows.all()}

    # duplicate review decisions ───────────────────────────────────────────────

    async def dismissed_pairs(
        self, user_id: uuid.UUID, project_id: uuid.UUID
    ) -> set[tuple[uuid.UUID, uuid.UUID]]:
        rows = await self._db.execute(
            select(
                ResearchPaperDuplicateReview.paper_a_id, ResearchPaperDuplicateReview.paper_b_id
            ).where(
                ResearchPaperDuplicateReview.user_id == user_id,
                ResearchPaperDuplicateReview.research_project_id == project_id,
                ResearchPaperDuplicateReview.decision == "not_duplicate",
            )
        )
        return {(a, b) for a, b in rows.tuples().all()}  # noqa: C416

    async def dismiss_pair(
        self, user_id: uuid.UUID, project_id: uuid.UUID, a: uuid.UUID, b: uuid.UUID
    ) -> None:
        first, second = sorted((a, b), key=str)
        await self._db.execute(
            pg_insert(ResearchPaperDuplicateReview)
            .values(
                user_id=user_id,
                research_project_id=project_id,
                paper_a_id=first,
                paper_b_id=second,
                decision="not_duplicate",
            )
            .on_conflict_do_nothing(constraint="uq_research_dup_pair")
        )
