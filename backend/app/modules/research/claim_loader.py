"""Loads the verified claims of analysed papers for the deterministic research tools. Ownership is
enforced by the scoped repositories: a paper that is not the caller's or not in the project is a
404, a paper without a completed analysis is a 422."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research import SECTIONS
from app.repositories.research_analysis_repository import ResearchAnalysisRepository
from app.repositories.research_paper_repository import ResearchPaperRepository
from app.research.claims import LoadedPaper, StoredClaim
from app.research.errors import PaperNotAnalysedError, PaperNotFoundError


async def load_analysed_papers(
    db: AsyncSession,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    paper_ids: list[uuid.UUID] | None,
) -> list[LoadedPaper]:
    """The given papers (or every non-archived paper of the project that has a completed analysis
    when `paper_ids` is None), each with its latest completed analysis."""
    papers = ResearchPaperRepository(db)
    analyses = ResearchAnalysisRepository(db)
    if paper_ids is None:
        rows, _ = await papers.list_for_project(
            user_id,
            project_id,
            q=None,
            status=None,
            year=None,
            has_file=None,
            archived=False,
            sort_by="created_at",
            descending=False,
            limit=100,
            offset=0,
        )
        found = {r[0].id: r[0] for r in rows if r[0].analysis_status == "analysed"}
        ordered = list(found)
    else:
        found = await papers.get_many(user_id, project_id, paper_ids)
        if len(found) != len(paper_ids):
            raise PaperNotFoundError()
        ordered = list(paper_ids)
    loaded: list[LoadedPaper] = []
    for paper_id in ordered:
        run = await analyses.latest_completed(user_id, paper_id)
        if run is None:
            raise PaperNotAnalysedError()
        evidence: dict[tuple[str, int], tuple[uuid.UUID, str, int | None, uuid.UUID | None]] = {}
        for ev in await analyses.evidence_for(user_id, run.id):
            evidence.setdefault(
                (ev.claim_type, ev.claim_index),
                (ev.id, ev.supporting_text, ev.page_number, ev.document_id),
            )
        sections = (run.structured_result or {}).get("sections", {})
        claims: list[StoredClaim] = []
        for name in SECTIONS:
            for item in sections.get(name, []):
                ev = evidence.get((name, item["index"]))
                claims.append(
                    StoredClaim(
                        paper_id=paper_id,
                        section=name,
                        index=item["index"],
                        label=item.get("label"),
                        text=item["text"],
                        origin=item["origin"],
                        evidence_id=ev[0] if ev else None,
                        quote=ev[1] if ev else None,
                        page_number=ev[2] if ev else None,
                        document_id=ev[3] if ev else None,
                    )
                )
        paper = found[paper_id]
        loaded.append(
            LoadedPaper(
                paper_id=paper_id,
                title=paper.title,
                year=paper.publication_year,
                extraction_id=run.id,
                version_number=run.version_number,
                claims=claims,
            )
        )
    return loaded


async def load_available(
    db: AsyncSession,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    paper_ids: list[uuid.UUID],
) -> tuple[set[uuid.UUID], dict[uuid.UUID, LoadedPaper]]:
    """(ids of those papers that are in the project, the subset with a completed analysis).
    Never raises for a missing paper or analysis: callers report both cases."""
    if not paper_ids:
        return set(), {}
    found = await ResearchPaperRepository(db).get_many(user_id, project_id, paper_ids)
    analysed: dict[uuid.UUID, LoadedPaper] = {}
    for pid in found:
        try:
            analysed[pid] = (await load_analysed_papers(db, user_id, project_id, [pid]))[0]
        except PaperNotAnalysedError:
            continue
    return set(found), analysed
