"""Concept link service (Phase 7 M7.10). Links connect analysed papers to knowledge nodes that
already exist in the project workspace; nothing is created in the graph and nothing is written to
the learner tables, so reading a paper can never raise a learner mastery value (spec 32.6)."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research import ResearchConceptLink
from app.modules.research.claim_loader import load_analysed_papers
from app.modules.research.concept_schemas import (
    ResearchConceptClaim,
    ResearchConceptGap,
    ResearchConceptLinkOut,
    ResearchConceptNodeRef,
    ResearchConceptPaper,
    ResearchConceptPaperRef,
    ResearchConceptResearchOut,
)
from app.repositories.research_concept_link_repository import ResearchConceptLinkRepository
from app.repositories.research_paper_repository import ResearchPaperRepository
from app.repositories.research_project_repository import ResearchProjectRepository
from app.research.claims import LoadedPaper
from app.research.concept_links import NodeNames, find_mentions
from app.research.errors import (
    ConceptLinkNotFoundError,
    ConceptNotFoundError,
    NoAnalysedPapersError,
    PaperNotAnalysedError,
    PaperNotFoundError,
    ProjectArchivedError,
    ProjectNotFoundError,
)

MAX_CLAIMS_PER_SECTION = 10
MAX_CONFIRMED_PAPERS = 20
SECTIONS = {
    "findings": "results",
    "methods": "methodology",
    "datasets": "dataset",
    "metrics": "evaluation",
}


def _out(row: tuple[ResearchConceptLink, str, str, str]) -> ResearchConceptLinkOut:
    link, paper_title, node_name, node_type = row
    return ResearchConceptLinkOut(
        id=link.id,
        research_project_id=link.research_project_id,
        paper=ResearchConceptPaperRef(id=link.research_paper_id, title=paper_title),
        node=ResearchConceptNodeRef(id=link.knowledge_node_id, name=node_name, node_type=node_type),
        match_kind=link.match_kind,
        matched_text=link.matched_text,
        link_status=link.link_status,
        claim_type=link.claim_type,
        claim_text=link.claim_text,
        evidence_id=link.research_evidence_id,
        document_id=link.document_id,
        page_number=link.page_number,
        mention_count=link.mention_count,
        created_at=link.created_at,
    )


class ResearchConceptService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._repo = ResearchConceptLinkRepository(db)

    async def _project(self, user_id: uuid.UUID, project_id: uuid.UUID, *, write: bool):  # type: ignore[no-untyped-def]
        project = await ResearchProjectRepository(self._db).get(user_id, project_id)
        if project is None:
            raise ProjectNotFoundError()
        if write and project.archived_at is not None:
            raise ProjectArchivedError()
        return project

    async def suggest(
        self, user_id: uuid.UUID, project_id: uuid.UUID, paper_ids: list[uuid.UUID] | None
    ) -> list[ResearchConceptLinkOut]:
        project = await self._project(user_id, project_id, write=True)
        papers = await load_analysed_papers(self._db, user_id, project_id, paper_ids)
        if not papers:
            raise NoAnalysedPapersError()
        nodes = [
            NodeNames(n.id, n.name, tuple(aliases))
            for n, aliases in await self._repo.nodes_in_workspace(user_id, project.workspace_id)
        ]
        existing = await self._repo.existing_pairs(user_id, [p.paper_id for p in papers])
        created: list[ResearchConceptLink] = []
        for m in find_mentions(papers, nodes):
            if (m.paper_id, m.node_id) in existing:
                continue  # already suggested, confirmed or rejected: a decision is never reset
            created.append(
                await self._repo.add(
                    ResearchConceptLink(
                        user_id=user_id,
                        research_project_id=project_id,
                        research_paper_id=m.paper_id,
                        knowledge_node_id=m.node_id,
                        match_kind=m.match_kind,
                        matched_text=m.matched_text,
                        link_status="suggested",
                        extraction_id=m.extraction_id,
                        research_evidence_id=m.claim.evidence_id,
                        document_id=m.claim.document_id,
                        page_number=m.claim.page_number,
                        claim_type=m.claim.section,
                        claim_text=m.claim.text,
                        mention_count=m.mention_count,
                    )
                )
            )
        await self._db.commit()
        rows, _ = await self._repo.list_for_project(
            user_id, project_id, paper_id=None, status=None, limit=100, offset=0
        )
        new_ids = {c.id for c in created}
        return [_out(r) for r in rows if r[0].id in new_ids]

    async def list(
        self,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        *,
        paper_id: uuid.UUID | None,
        status: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[ResearchConceptLinkOut], int]:
        await self._project(user_id, project_id, write=False)
        rows, total = await self._repo.list_for_project(
            user_id, project_id, paper_id=paper_id, status=status, limit=limit, offset=offset
        )
        return [_out(r) for r in rows], total

    async def _link(self, user_id: uuid.UUID, link_id: uuid.UUID) -> ResearchConceptLink:
        link = await self._repo.get(user_id, link_id)
        if link is None:
            raise ConceptLinkNotFoundError()
        return link

    async def set_status(
        self, user_id: uuid.UUID, link_id: uuid.UUID, status: str
    ) -> ResearchConceptLinkOut:
        link = await self._link(user_id, link_id)
        await self._project(user_id, link.research_project_id, write=True)
        link.link_status = status
        await self._db.commit()
        rows, _ = await self._repo.list_for_project(
            user_id,
            link.research_project_id,
            paper_id=link.research_paper_id,
            status=None,
            limit=100,
            offset=0,
        )
        return _out(next(r for r in rows if r[0].id == link_id))

    async def delete(self, user_id: uuid.UUID, link_id: uuid.UUID) -> None:
        link = await self._link(user_id, link_id)
        await self._project(user_id, link.research_project_id, write=True)
        await self._repo.delete(user_id, link_id)
        await self._db.commit()

    async def for_paper(
        self, user_id: uuid.UUID, paper_id: uuid.UUID
    ) -> list[ResearchConceptLinkOut]:
        if await ResearchPaperRepository(self._db).get(user_id, paper_id) is None:
            raise PaperNotFoundError()
        return [_out(r) for r in await self._repo.for_paper(user_id, paper_id)]

    async def concept_research(
        self, user_id: uuid.UUID, node_id: uuid.UUID
    ) -> ResearchConceptResearchOut:
        node = await self._repo.node(user_id, node_id)
        if node is None:
            raise ConceptNotFoundError()
        rows = await self._repo.for_node(user_id, node_id)
        papers = [
            ResearchConceptPaper(
                link_id=link.id,
                paper_id=link.research_paper_id,
                paper_title=paper_title,
                research_project_id=link.research_project_id,
                project_title=project_title,
                link_status=link.link_status,
                matched_text=link.matched_text,
            )
            for link, paper_title, project_title in rows
        ]
        confirmed = [link for link, _, _ in rows if link.link_status == "confirmed"]
        sections: dict[str, list[ResearchConceptClaim]] = {k: [] for k in SECTIONS}
        confirmed_ids: list[uuid.UUID] = []
        for link in confirmed[:MAX_CONFIRMED_PAPERS]:
            loaded: LoadedPaper
            try:
                loaded = (
                    await load_analysed_papers(
                        self._db, user_id, link.research_project_id, [link.research_paper_id]
                    )
                )[0]
            except (PaperNotAnalysedError, PaperNotFoundError):
                continue
            confirmed_ids.append(link.research_paper_id)
            for key, section in SECTIONS.items():
                for c in loaded.in_section(section):
                    if len(sections[key]) < MAX_CLAIMS_PER_SECTION:
                        sections[key].append(
                            ResearchConceptClaim(
                                paper_id=loaded.paper_id,
                                paper_title=loaded.title,
                                claim_text=c.text,
                                quote=c.quote,
                                page_number=c.page_number,
                            )
                        )
        gaps = await self._repo.gaps_for_papers(user_id, confirmed_ids)
        return ResearchConceptResearchOut(
            node=ResearchConceptNodeRef(id=node.id, name=node.name, node_type=node.node_type),
            papers=papers,
            findings=sections["findings"],
            methods=sections["methods"],
            datasets=sections["datasets"],
            metrics=sections["metrics"],
            gaps=[
                ResearchConceptGap(
                    id=g.id,
                    research_project_id=g.research_project_id,
                    title=g.title,
                    category=g.category,
                    confidence_label=g.confidence_label,
                    validation_status=g.validation_status,
                )
                for g in gaps
            ],
        )
