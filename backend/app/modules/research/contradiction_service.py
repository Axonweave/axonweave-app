"""Contradiction service (Phase 7 M7.7). Deterministic candidates from
`app.research.contradictions`; no model call. Regeneration replaces only candidates the researcher
has not reviewed or annotated; reviewed records are kept and not duplicated."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research import ResearchContradiction
from app.modules.research.claim_loader import load_analysed_papers
from app.modules.research.contradiction_schemas import (
    ResearchContradictionOut,
    ResearchContradictionPatch,
    ResearchContradictionSide,
)
from app.repositories.research_contradiction_repository import ResearchContradictionRepository
from app.repositories.research_paper_repository import ResearchPaperRepository
from app.repositories.research_project_repository import ResearchProjectRepository
from app.research.contradictions import ANALYSIS_VERSION, generate_candidates
from app.research.errors import (
    ContradictionNotFoundError,
    NeedTwoAnalysedPapersError,
    ProjectArchivedError,
    ProjectNotFoundError,
)


class ResearchContradictionService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._repo = ResearchContradictionRepository(db)

    async def _project(self, user_id: uuid.UUID, project_id: uuid.UUID, *, write: bool) -> None:
        project = await ResearchProjectRepository(self._db).get(user_id, project_id)
        if project is None:
            raise ProjectNotFoundError()
        if write and project.archived_at is not None:
            raise ProjectArchivedError()

    async def _out(
        self, user_id: uuid.UUID, project_id: uuid.UUID, rows: list[ResearchContradiction]
    ) -> list[ResearchContradictionOut]:
        ids = {r.paper_a_id for r in rows} | {r.paper_b_id for r in rows}
        found = (
            await ResearchPaperRepository(self._db).get_many(user_id, project_id, list(ids))
            if ids
            else {}
        )

        def title(pid: uuid.UUID) -> str:
            return found[pid].title if pid in found else "Paper"

        return [
            ResearchContradictionOut(
                id=r.id,
                research_project_id=r.research_project_id,
                claim_a=ResearchContradictionSide(
                    paper_id=r.paper_a_id,
                    paper_title=title(r.paper_a_id),
                    claim_type=r.claim_a_type,
                    claim_text=r.claim_a_text,
                    evidence_id=r.evidence_a_id,
                    quote=r.quote_a,
                    page_number=r.page_a,
                ),
                claim_b=ResearchContradictionSide(
                    paper_id=r.paper_b_id,
                    paper_title=title(r.paper_b_id),
                    claim_type=r.claim_b_type,
                    claim_text=r.claim_b_text,
                    evidence_id=r.evidence_b_id,
                    quote=r.quote_b,
                    page_number=r.page_b,
                ),
                conditions=r.conditions,
                category=r.category,
                explanation=r.explanation,
                confidence_label=r.confidence_label,
                review_status=r.review_status,
                researcher_explanation=r.researcher_explanation,
                analysis_version=r.analysis_version,
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
            for r in rows
        ]

    async def generate(
        self, user_id: uuid.UUID, project_id: uuid.UUID, paper_ids: list[uuid.UUID] | None
    ) -> list[ResearchContradictionOut]:
        await self._project(user_id, project_id, write=True)
        papers = await load_analysed_papers(self._db, user_id, project_id, paper_ids)
        if len(papers) < 2:
            raise NeedTwoAnalysedPapersError()
        existing = await self._repo.all_for_project(user_id, project_id)
        stale = [
            r.id
            for r in existing
            if r.review_status == "unreviewed" and not r.researcher_explanation
        ]
        stale_set = set(stale)
        kept = {r.fingerprint for r in existing if r.id not in stale_set}
        await self._repo.delete_many(user_id, stale)
        created: list[ResearchContradiction] = []
        for cand in generate_candidates(papers):
            if cand.fingerprint in kept:
                continue
            a, b = cand.claim_a, cand.claim_b
            created.append(
                await self._repo.add(
                    ResearchContradiction(
                        user_id=user_id,
                        research_project_id=project_id,
                        paper_a_id=a.paper_id,
                        paper_b_id=b.paper_id,
                        claim_a_text=a.text,
                        claim_b_text=b.text,
                        claim_a_type=a.section,
                        claim_b_type=b.section,
                        evidence_a_id=a.evidence_id,
                        evidence_b_id=b.evidence_id,
                        quote_a=a.quote,
                        quote_b=b.quote,
                        page_a=a.page_number,
                        page_b=b.page_number,
                        conditions={**cand.conditions, "shared_terms": cand.shared_terms},
                        category=cand.category,
                        explanation=cand.explanation,
                        confidence_label=cand.confidence_label,
                        review_status="unreviewed",
                        analysis_version=ANALYSIS_VERSION,
                        fingerprint=cand.fingerprint,
                    )
                )
            )
        await self._db.commit()
        return await self._out(user_id, project_id, created)

    async def list(
        self,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        *,
        category: str | None,
        review_status: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[ResearchContradictionOut], int]:
        await self._project(user_id, project_id, write=False)
        rows, total = await self._repo.list_for_project(
            user_id,
            project_id,
            category=category,
            review_status=review_status,
            limit=limit,
            offset=offset,
        )
        return await self._out(user_id, project_id, rows), total

    async def _get(self, user_id: uuid.UUID, contradiction_id: uuid.UUID) -> ResearchContradiction:
        row = await self._repo.get(user_id, contradiction_id)
        if row is None:
            raise ContradictionNotFoundError()
        return row

    async def get(
        self, user_id: uuid.UUID, contradiction_id: uuid.UUID
    ) -> ResearchContradictionOut:
        row = await self._get(user_id, contradiction_id)
        return (await self._out(user_id, row.research_project_id, [row]))[0]

    async def patch(
        self, user_id: uuid.UUID, contradiction_id: uuid.UUID, body: ResearchContradictionPatch
    ) -> ResearchContradictionOut:
        row = await self._get(user_id, contradiction_id)
        await self._project(user_id, row.research_project_id, write=True)
        changes = body.model_dump(exclude_unset=True)
        if changes.get("review_status") is not None:
            row.review_status = changes["review_status"]
        if "researcher_explanation" in changes:
            row.researcher_explanation = changes["researcher_explanation"] or None
        await self._db.commit()
        await self._db.refresh(row)
        return (await self._out(user_id, row.research_project_id, [row]))[0]

    async def delete(self, user_id: uuid.UUID, contradiction_id: uuid.UUID) -> None:
        row = await self._get(user_id, contradiction_id)
        await self._project(user_id, row.research_project_id, write=True)
        await self._repo.delete(user_id, contradiction_id)
        await self._db.commit()
