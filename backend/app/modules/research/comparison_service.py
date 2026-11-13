"""Paper comparison service (Phase 7 M7.4). Order of checks (CLAUDE.md rule 1): the project is this
user's (404) and not archived -> every selected paper is this user's and in this project (404
otherwise, so ids from other projects or users are indistinguishable from missing ones) -> every
paper has a completed analysis (422) -> build, save. No model call is made."""

from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research import SECTIONS, ResearchComparison, ResearchComparisonPaper
from app.modules.research.comparison_schemas import (
    ResearchComparisonCreate,
    ResearchComparisonOut,
    ResearchComparisonPatch,
    ResearchComparisonSummary,
)
from app.repositories.research_analysis_repository import ResearchAnalysisRepository
from app.repositories.research_comparison_repository import ResearchComparisonRepository
from app.repositories.research_paper_repository import ResearchPaperRepository
from app.repositories.research_project_repository import ResearchProjectRepository
from app.research.comparison import ClaimInput, PaperInput, build_comparison
from app.research.errors import (
    ComparisonNotFoundError,
    PaperNotAnalysedError,
    PaperNotFoundError,
    ProjectArchivedError,
    ProjectNotFoundError,
)


def to_out(row: ResearchComparison, paper_ids: list[uuid.UUID]) -> ResearchComparisonOut:
    return ResearchComparisonOut(
        id=row.id,
        research_project_id=row.research_project_id,
        title=row.title,
        paper_ids=paper_ids,
        configuration=row.comparison_configuration,
        result=row.comparison_result,
        notes={k: str(v) for k, v in (row.notes or {}).items()},
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class ResearchComparisonService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._repo = ResearchComparisonRepository(db)

    async def _project(self, user_id: uuid.UUID, project_id: uuid.UUID) -> Any:
        project = await ResearchProjectRepository(self._db).get(user_id, project_id)
        if project is None:
            raise ProjectNotFoundError()
        return project

    async def _owned(self, user_id: uuid.UUID, comparison_id: uuid.UUID) -> ResearchComparison:
        row = await self._repo.get(user_id, comparison_id)
        if row is None:
            raise ComparisonNotFoundError()
        return row

    async def create(
        self, user_id: uuid.UUID, project_id: uuid.UUID, body: ResearchComparisonCreate
    ) -> ResearchComparisonOut:
        project = await self._project(user_id, project_id)
        if project.archived_at is not None:
            raise ProjectArchivedError()
        found = await ResearchPaperRepository(self._db).get_many(
            user_id, project_id, list(body.paper_ids)
        )
        if len(found) != len(body.paper_ids):
            raise PaperNotFoundError()
        analyses = ResearchAnalysisRepository(self._db)
        inputs: list[PaperInput] = []
        for paper_id in body.paper_ids:
            run = await analyses.latest_completed(user_id, paper_id)
            if run is None:
                raise PaperNotAnalysedError()
            evidence: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
            for ev in await analyses.evidence_for(user_id, run.id):
                evidence[(ev.claim_type, ev.claim_index)].append(
                    {
                        "quote": ev.supporting_text,
                        "page_number": ev.page_number,
                        "document_id": str(ev.document_id) if ev.document_id else None,
                    }
                )
            sections = (run.structured_result or {}).get("sections", {})
            claims = {
                name: [
                    ClaimInput(
                        text=item["text"],
                        label=item.get("label"),
                        origin=item["origin"],
                        evidence=evidence.get((name, item["index"]), []),
                    )
                    for item in sections.get(name, [])
                ]
                for name in SECTIONS
            }
            inputs.append(
                PaperInput(
                    str(paper_id), found[paper_id].title, str(run.id), run.version_number, claims
                )
            )
        result = build_comparison(inputs, body.dimensions)
        row = await self._repo.add(
            ResearchComparison(
                user_id=user_id,
                research_project_id=project_id,
                title=body.title,
                comparison_configuration={
                    "paper_ids": [str(i) for i in body.paper_ids],
                    "dimensions": body.dimensions or [r["dimension"] for r in result["rows"]],
                },
                comparison_result=result,
                notes={},
            ),
            [
                ResearchComparisonPaper(
                    user_id=user_id,
                    research_paper_id=uuid.UUID(p.paper_id),
                    extraction_id=uuid.UUID(p.extraction_id),
                    position=i,
                )
                for i, p in enumerate(inputs)
            ],
        )
        await self._db.commit()
        await self._db.refresh(row)
        return to_out(row, list(body.paper_ids))

    async def list(
        self, user_id: uuid.UUID, project_id: uuid.UUID, *, limit: int, offset: int
    ) -> tuple[list[ResearchComparisonSummary], int]:
        await self._project(user_id, project_id)
        rows, total = await self._repo.list_for_project(
            user_id, project_id, limit=limit, offset=offset
        )
        return [
            ResearchComparisonSummary(
                id=r.id,
                research_project_id=r.research_project_id,
                title=r.title,
                paper_count=len(r.comparison_configuration.get("paper_ids", [])),
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
            for r in rows
        ], total

    async def get(self, user_id: uuid.UUID, comparison_id: uuid.UUID) -> ResearchComparisonOut:
        row = await self._owned(user_id, comparison_id)
        return to_out(row, await self._repo.paper_ids(user_id, comparison_id))

    async def patch(
        self, user_id: uuid.UUID, comparison_id: uuid.UUID, body: ResearchComparisonPatch
    ) -> ResearchComparisonOut:
        row = await self._owned(user_id, comparison_id)
        if body.title is not None:
            row.title = body.title
        if body.notes is not None:
            # Blank text removes a note. The extracted result is never touched.
            row.notes = {k: v for k, v in body.notes.items() if v}
        await self._db.commit()
        await self._db.refresh(row)
        return to_out(row, await self._repo.paper_ids(user_id, comparison_id))

    async def delete(self, user_id: uuid.UUID, comparison_id: uuid.UUID) -> None:
        await self._owned(user_id, comparison_id)
        await self._repo.delete(user_id, comparison_id)
        await self._db.commit()
