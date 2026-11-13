"""Research gap service (Phase 7 M7.6). Candidates come from the deterministic engine in
`app.research.gaps`; nothing here calls a model. Regeneration replaces only gaps that are still
untouched suggestions; anything the researcher accepted, rejected, edited or annotated is kept and
its candidate is not duplicated."""

from __future__ import annotations

import uuid
from collections import defaultdict

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research import ResearchGap, ResearchGapEvidence
from app.modules.research.claim_loader import load_analysed_papers
from app.modules.research.gap_schemas import (
    ResearchGapEvidenceOut,
    ResearchGapOut,
    ResearchGapPatch,
)
from app.repositories.research_gap_repository import ResearchGapRepository
from app.repositories.research_project_repository import ResearchProjectRepository
from app.research.claims import StoredClaim
from app.research.errors import (
    GapNotFoundError,
    NoAnalysedPapersError,
    ProjectArchivedError,
    ProjectNotFoundError,
)
from app.research.gaps import ANALYSIS_VERSION, generate_candidates

MAX_EVIDENCE_PER_ROLE = 12


def _evidence_row(
    user_id: uuid.UUID, gap_id: uuid.UUID, role: str, c: StoredClaim
) -> ResearchGapEvidence:
    return ResearchGapEvidence(
        user_id=user_id,
        gap_id=gap_id,
        research_paper_id=c.paper_id,
        research_evidence_id=c.evidence_id,
        evidence_role=role,
        claim_type=c.section,
        claim_text=c.text,
    )


class ResearchGapService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._repo = ResearchGapRepository(db)

    async def _project(self, user_id: uuid.UUID, project_id: uuid.UUID, *, write: bool) -> None:
        project = await ResearchProjectRepository(self._db).get(user_id, project_id)
        if project is None:
            raise ProjectNotFoundError()
        if write and project.archived_at is not None:
            raise ProjectArchivedError()

    async def _out(self, user_id: uuid.UUID, gaps: list[ResearchGap]) -> list[ResearchGapOut]:
        rows = await self._repo.evidence_for(user_id, [g.id for g in gaps])
        by_gap: dict[uuid.UUID, list[ResearchGapEvidence]] = defaultdict(list)
        for r in rows:
            by_gap[r.gap_id].append(r)
        return [
            ResearchGapOut(
                id=g.id,
                research_project_id=g.research_project_id,
                title=g.title,
                description=g.description,
                category=g.category,
                rationale=g.rationale,
                confidence_label=g.confidence_label,
                limitations=g.limitations,
                suggested_direction=g.suggested_direction,
                validation_status=g.validation_status,
                analysis_version=g.analysis_version,
                edited_by_user=g.edited_by_user,
                researcher_notes=g.researcher_notes,
                created_at=g.created_at,
                updated_at=g.updated_at,
                evidence=[ResearchGapEvidenceOut.model_validate(r) for r in by_gap[g.id]],
            )
            for g in gaps
        ]

    async def generate(
        self, user_id: uuid.UUID, project_id: uuid.UUID, paper_ids: list[uuid.UUID] | None
    ) -> list[ResearchGapOut]:
        await self._project(user_id, project_id, write=True)
        papers = await load_analysed_papers(self._db, user_id, project_id, paper_ids)
        if not papers:
            raise NoAnalysedPapersError()
        existing = await self._repo.all_for_project(user_id, project_id)
        stale = [
            g.id
            for g in existing
            if g.validation_status == "suggested"
            and not g.edited_by_user
            and not g.researcher_notes
        ]
        stale_set = set(stale)
        kept = {g.fingerprint for g in existing if g.id not in stale_set}
        await self._repo.delete_many(user_id, stale)
        created: list[ResearchGap] = []
        for cand in generate_candidates(papers):
            if cand.fingerprint in kept:
                continue
            gap = await self._repo.add(
                ResearchGap(
                    user_id=user_id,
                    research_project_id=project_id,
                    title=cand.title,
                    description=cand.description,
                    category=cand.category,
                    rationale=cand.rationale,
                    confidence_label=cand.confidence_label,
                    limitations=cand.limitations,
                    suggested_direction=cand.suggested_direction,
                    validation_status="suggested",
                    analysis_version=ANALYSIS_VERSION,
                    fingerprint=cand.fingerprint,
                    edited_by_user=False,
                )
            )
            rows = [
                _evidence_row(user_id, gap.id, role, c)
                for role, claims in (
                    ("supporting", cand.supporting),
                    ("counter_evidence", cand.counter),
                )
                for c in claims[:MAX_EVIDENCE_PER_ROLE]
            ]
            await self._repo.add_evidence(rows)
            created.append(gap)
        await self._db.commit()
        return await self._out(user_id, created)

    async def list(
        self,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        *,
        category: str | None,
        status: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[ResearchGapOut], int]:
        await self._project(user_id, project_id, write=False)
        gaps, total = await self._repo.list_for_project(
            user_id, project_id, category=category, status=status, limit=limit, offset=offset
        )
        return await self._out(user_id, gaps), total

    async def _get(self, user_id: uuid.UUID, gap_id: uuid.UUID) -> ResearchGap:
        gap = await self._repo.get(user_id, gap_id)
        if gap is None:
            raise GapNotFoundError()
        return gap

    async def get(self, user_id: uuid.UUID, gap_id: uuid.UUID) -> ResearchGapOut:
        gap = await self._get(user_id, gap_id)
        return (await self._out(user_id, [gap]))[0]

    async def patch(
        self, user_id: uuid.UUID, gap_id: uuid.UUID, body: ResearchGapPatch
    ) -> ResearchGapOut:
        gap = await self._get(user_id, gap_id)
        await self._project(user_id, gap.research_project_id, write=True)
        changes = body.model_dump(exclude_unset=True)
        for key in ("title", "description", "suggested_direction"):
            if changes.get(key) is not None and changes[key] != getattr(gap, key):
                setattr(gap, key, changes[key])
                gap.edited_by_user = True
        if changes.get("validation_status") is not None:
            gap.validation_status = changes["validation_status"]
        if "researcher_notes" in changes:
            gap.researcher_notes = changes["researcher_notes"] or None
        await self._db.commit()
        await self._db.refresh(gap)
        return (await self._out(user_id, [gap]))[0]

    async def delete(self, user_id: uuid.UUID, gap_id: uuid.UUID) -> None:
        gap = await self._get(user_id, gap_id)
        await self._project(user_id, gap.research_project_id, write=True)
        await self._repo.delete(user_id, gap_id)
        await self._db.commit()
