"""Persistence for evidence matrices (Phase 7 M7.5). Every query is scoped by `user_id` (rule 3)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research import (
    ResearchEvidence,
    ResearchEvidenceMatrix,
    ResearchEvidenceMatrixColumn,
    ResearchEvidenceMatrixEntry,
)

M = ResearchEvidenceMatrix
C = ResearchEvidenceMatrixColumn
E = ResearchEvidenceMatrixEntry


class ResearchMatrixRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # matrices ────────────────────────────────────────────────────────────────

    async def get(self, user_id: uuid.UUID, matrix_id: uuid.UUID) -> M | None:
        return (
            await self._db.execute(select(M).where(M.user_id == user_id, M.id == matrix_id))
        ).scalar_one_or_none()

    async def list_for_project(
        self, user_id: uuid.UUID, project_id: uuid.UUID, *, limit: int, offset: int
    ) -> tuple[list[M], int]:
        where = (M.user_id == user_id, M.research_project_id == project_id)
        total = (await self._db.execute(select(func.count(M.id)).where(*where))).scalar_one()
        rows = (
            await self._db.execute(
                select(M)
                .where(*where)
                .order_by(M.updated_at.desc(), M.id)
                .limit(limit)
                .offset(offset)
            )
        ).scalars()
        return list(rows), total

    async def add(self, matrix: M) -> M:
        self._db.add(matrix)
        await self._db.flush()
        return matrix

    async def delete(self, user_id: uuid.UUID, matrix_id: uuid.UUID) -> None:
        await self._db.execute(delete(M).where(M.user_id == user_id, M.id == matrix_id))

    async def count_papers(self, matrix_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, int]:
        if not matrix_ids:
            return {}
        rows = await self._db.execute(
            select(E.matrix_id, func.count(func.distinct(E.research_paper_id)))
            .where(E.matrix_id.in_(matrix_ids))
            .group_by(E.matrix_id)
        )
        return {m: int(n) for m, n in rows.all()}

    # columns ─────────────────────────────────────────────────────────────────

    async def columns(self, user_id: uuid.UUID, matrix_id: uuid.UUID) -> list[C]:
        rows = await self._db.execute(
            select(C)
            .where(C.user_id == user_id, C.matrix_id == matrix_id)
            .order_by(C.position, C.id)
        )
        return list(rows.scalars())

    async def get_column(
        self, user_id: uuid.UUID, matrix_id: uuid.UUID, column_id: uuid.UUID
    ) -> C | None:
        return (
            await self._db.execute(
                select(C).where(C.user_id == user_id, C.matrix_id == matrix_id, C.id == column_id)
            )
        ).scalar_one_or_none()

    async def add_column(self, column: C) -> C:
        self._db.add(column)
        await self._db.flush()
        return column

    async def delete_column(self, user_id: uuid.UUID, column_id: uuid.UUID) -> None:
        await self._db.execute(delete(C).where(C.user_id == user_id, C.id == column_id))

    # entries ─────────────────────────────────────────────────────────────────

    async def entries(self, user_id: uuid.UUID, matrix_id: uuid.UUID) -> list[E]:
        rows = await self._db.execute(
            select(E).where(E.user_id == user_id, E.matrix_id == matrix_id)
        )
        return list(rows.scalars())

    async def get_entry(
        self, user_id: uuid.UUID, matrix_id: uuid.UUID, paper_id: uuid.UUID, column_id: uuid.UUID
    ) -> E | None:
        return (
            await self._db.execute(
                select(E).where(
                    E.user_id == user_id,
                    E.matrix_id == matrix_id,
                    E.research_paper_id == paper_id,
                    E.column_id == column_id,
                )
            )
        ).scalar_one_or_none()

    async def add_entries(self, entries: Sequence[E]) -> None:
        self._db.add_all(entries)
        await self._db.flush()

    async def remove_paper(
        self, user_id: uuid.UUID, matrix_id: uuid.UUID, paper_id: uuid.UUID
    ) -> int:
        result = await self._db.execute(
            delete(E).where(
                E.user_id == user_id, E.matrix_id == matrix_id, E.research_paper_id == paper_id
            )
        )
        return int(result.rowcount)

    # evidence lookup ─────────────────────────────────────────────────────────

    async def evidence_by_ids(
        self, user_id: uuid.UUID, ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, ResearchEvidence]:
        if not ids:
            return {}
        rows = await self._db.execute(
            select(ResearchEvidence).where(
                ResearchEvidence.user_id == user_id, ResearchEvidence.id.in_(ids)
            )
        )
        return {r.id: r for r in rows.scalars()}
