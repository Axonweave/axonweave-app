"""Persistence for paper analyses and researcher notes (Phase 7 M7.3).

The worker-side job methods (claim, stage, heartbeat, cancel, finish, stale sweep) are inherited
from `KnowledgeJobRepository`, pointed at `research_paper_extractions`. User-facing reads are
always scoped by `user_id` (rule 3): a foreign paper, analysis or note is simply not found.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.sql import exists

from app.models.research import (
    ACTIVE_EXTRACTION_STATUSES,
    ResearchEvidence,
    ResearchPaper,
    ResearchPaperExtraction,
    ResearchPaperNote,
)
from app.repositories.knowledge_job_repository import KnowledgeJobRepository

E = ResearchPaperExtraction


class ResearchAnalysisRepository(KnowledgeJobRepository):
    _m: Any = ResearchPaperExtraction
    _cancel_code = "RESEARCH_CANCELLED"

    # analyses ────────────────────────────────────────────────────────────────

    async def get_for_paper(
        self, user_id: uuid.UUID, paper_id: uuid.UUID, extraction_id: uuid.UUID
    ) -> ResearchPaperExtraction | None:
        return (
            await self._db.execute(
                select(E).where(
                    E.id == extraction_id, E.user_id == user_id, E.research_paper_id == paper_id
                )
            )
        ).scalar_one_or_none()

    async def list_for_paper(
        self, user_id: uuid.UUID, paper_id: uuid.UUID, *, limit: int, offset: int
    ) -> tuple[list[ResearchPaperExtraction], int]:
        where = (E.user_id == user_id, E.research_paper_id == paper_id)
        total = (await self._db.execute(select(func.count(E.id)).where(*where))).scalar_one()
        rows = (
            await self._db.execute(
                select(E)
                .where(*where)
                .order_by(E.version_number.desc())
                .limit(limit)
                .offset(offset)
            )
        ).scalars()
        return list(rows), total

    async def active_for_paper(
        self, user_id: uuid.UUID, paper_id: uuid.UUID
    ) -> ResearchPaperExtraction | None:
        return (
            await self._db.execute(
                select(E).where(
                    E.user_id == user_id,
                    E.research_paper_id == paper_id,
                    E.status.in_(ACTIVE_EXTRACTION_STATUSES),
                )
            )
        ).scalar_one_or_none()

    async def latest_completed(
        self, user_id: uuid.UUID, paper_id: uuid.UUID
    ) -> ResearchPaperExtraction | None:
        return (
            await self._db.execute(
                select(E)
                .where(
                    E.user_id == user_id,
                    E.research_paper_id == paper_id,
                    E.status == "completed",
                )
                .order_by(E.version_number.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    async def completed_version(
        self, user_id: uuid.UUID, paper_id: uuid.UUID, version: int
    ) -> ResearchPaperExtraction | None:
        return (
            await self._db.execute(
                select(E).where(
                    E.user_id == user_id,
                    E.research_paper_id == paper_id,
                    E.version_number == version,
                    E.status == "completed",
                )
            )
        ).scalar_one_or_none()

    async def next_version(self, paper_id: uuid.UUID) -> int:
        top = (
            await self._db.execute(
                select(func.max(E.version_number)).where(E.research_paper_id == paper_id)
            )
        ).scalar_one()
        return int(top or 0) + 1

    async def count_active_for_user(self, user_id: uuid.UUID) -> int:
        return await self.count_active(user_id)

    # evidence ────────────────────────────────────────────────────────────────

    async def evidence_for(
        self, user_id: uuid.UUID, extraction_id: uuid.UUID
    ) -> list[ResearchEvidence]:
        rows = await self._db.execute(
            select(ResearchEvidence)
            .where(
                ResearchEvidence.user_id == user_id,
                ResearchEvidence.extraction_id == extraction_id,
            )
            .order_by(
                ResearchEvidence.claim_type,
                ResearchEvidence.claim_index,
                ResearchEvidence.created_at,
                ResearchEvidence.id,
            )
        )
        return list(rows.scalars())

    async def add_evidence(self, rows: Sequence[ResearchEvidence]) -> None:
        self._db.add_all(rows)
        await self._db.flush()

    # paper status ────────────────────────────────────────────────────────────

    async def paper_project_id(self, paper_id: uuid.UUID) -> uuid.UUID | None:
        return (
            await self._db.execute(
                select(ResearchPaper.research_project_id).where(ResearchPaper.id == paper_id)
            )
        ).scalar_one_or_none()

    async def refresh_paper_status(self, paper_id: uuid.UUID) -> None:
        """Derive the paper's `analysis_status` from its runs: an active run wins, then a
        completed one (a later failed re-run does not hide the earlier result), then failed."""
        active = (
            await self._db.execute(
                select(E.status).where(
                    E.research_paper_id == paper_id, E.status.in_(ACTIVE_EXTRACTION_STATUSES)
                )
            )
        ).scalar_one_or_none()
        if active is not None:
            status = "queued" if active == "pending" else "analysing"
        else:
            has = {
                name: (
                    await self._db.execute(
                        select(exists().where(E.research_paper_id == paper_id, E.status == name))
                    )
                ).scalar_one()
                for name in ("completed", "failed")
            }
            status = (
                "analysed" if has["completed"] else "failed" if has["failed"] else "not_analysed"
            )
        await self._db.execute(
            update(ResearchPaper).where(ResearchPaper.id == paper_id).values(analysis_status=status)
        )

    async def refresh_stuck_paper_statuses(self) -> int:
        """Papers still marked queued/analysing whose run is no longer active (the stale sweeper
        failed it, or it was removed): derive their status again."""
        stuck = (
            await self._db.execute(
                select(ResearchPaper.id).where(
                    ResearchPaper.analysis_status.in_(("queued", "analysing")),
                    ~exists().where(
                        E.research_paper_id == ResearchPaper.id,
                        E.status.in_(ACTIVE_EXTRACTION_STATUSES),
                    ),
                )
            )
        ).scalars()
        ids = list(stuck)
        for paper_id in ids:
            await self.refresh_paper_status(paper_id)
        return len(ids)

    # notes ───────────────────────────────────────────────────────────────────

    async def list_notes(self, user_id: uuid.UUID, paper_id: uuid.UUID) -> list[ResearchPaperNote]:
        rows = await self._db.execute(
            select(ResearchPaperNote)
            .where(
                ResearchPaperNote.user_id == user_id,
                ResearchPaperNote.research_paper_id == paper_id,
            )
            .order_by(ResearchPaperNote.created_at.desc(), ResearchPaperNote.id)
        )
        return list(rows.scalars())

    async def get_note(self, user_id: uuid.UUID, note_id: uuid.UUID) -> ResearchPaperNote | None:
        return (
            await self._db.execute(
                select(ResearchPaperNote).where(
                    ResearchPaperNote.id == note_id, ResearchPaperNote.user_id == user_id
                )
            )
        ).scalar_one_or_none()

    async def add_note(self, note: ResearchPaperNote) -> ResearchPaperNote:
        self._db.add(note)
        await self._db.flush()
        return note

    async def delete_note(self, user_id: uuid.UUID, note_id: uuid.UUID) -> None:
        await self._db.execute(
            delete(ResearchPaperNote).where(
                ResearchPaperNote.id == note_id, ResearchPaperNote.user_id == user_id
            )
        )
