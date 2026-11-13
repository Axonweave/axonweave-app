"""Persistence for concept links (Phase 7 M7.10). Every query is scoped by `user_id` (rule 3). The
knowledge tables are only read here; nothing in the graph or the learner tables is written."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeNode, KnowledgeNodeAlias
from app.models.research import (
    ResearchConceptLink,
    ResearchGap,
    ResearchGapEvidence,
    ResearchPaper,
    ResearchProject,
)

L = ResearchConceptLink
N = KnowledgeNode

MAX_NODES = 3000


class ResearchConceptLinkRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # knowledge (read only) ───────────────────────────────────────────────────

    async def node(self, user_id: uuid.UUID, node_id: uuid.UUID) -> N | None:
        return (
            await self._db.execute(
                select(N).where(N.user_id == user_id, N.id == node_id, N.archived_at.is_(None))
            )
        ).scalar_one_or_none()

    async def nodes_in_workspace(
        self, user_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> list[tuple[N, list[str]]]:
        nodes = (
            await self._db.execute(
                select(N)
                .where(
                    N.user_id == user_id, N.workspace_id == workspace_id, N.archived_at.is_(None)
                )
                .order_by(N.name)
                .limit(MAX_NODES)
            )
        ).scalars()
        listed = list(nodes)
        if not listed:
            return []
        aliases = (
            await self._db.execute(
                select(KnowledgeNodeAlias.knowledge_node_id, KnowledgeNodeAlias.alias).where(
                    KnowledgeNodeAlias.user_id == user_id,
                    KnowledgeNodeAlias.knowledge_node_id.in_([n.id for n in listed]),
                )
            )
        ).all()
        by_node: dict[uuid.UUID, list[str]] = {}
        for node_id, alias in aliases:
            by_node.setdefault(node_id, []).append(alias)
        return [(n, by_node.get(n.id, [])) for n in listed]

    # links ───────────────────────────────────────────────────────────────────

    async def get(self, user_id: uuid.UUID, link_id: uuid.UUID) -> L | None:
        return (
            await self._db.execute(select(L).where(L.user_id == user_id, L.id == link_id))
        ).scalar_one_or_none()

    async def existing_pairs(
        self, user_id: uuid.UUID, paper_ids: Sequence[uuid.UUID]
    ) -> set[tuple[uuid.UUID, uuid.UUID]]:
        if not paper_ids:
            return set()
        rows = await self._db.execute(
            select(L.research_paper_id, L.knowledge_node_id).where(
                L.user_id == user_id, L.research_paper_id.in_(paper_ids)
            )
        )
        return set(rows.tuples().all())

    async def add(self, link: L) -> L:
        self._db.add(link)
        await self._db.flush()
        return link

    async def delete(self, user_id: uuid.UUID, link_id: uuid.UUID) -> None:
        await self._db.execute(delete(L).where(L.user_id == user_id, L.id == link_id))

    async def list_for_project(
        self,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        *,
        paper_id: uuid.UUID | None,
        status: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[tuple[L, str, str, str]], int]:
        """(link, paper title, node name, node type) rows, newest first."""
        where = [L.user_id == user_id, L.research_project_id == project_id]
        if paper_id:
            where.append(L.research_paper_id == paper_id)
        if status:
            where.append(L.link_status == status)
        total = (await self._db.execute(select(func.count(L.id)).where(*where))).scalar_one()
        rows = await self._db.execute(
            select(L, ResearchPaper.title, N.name, N.node_type)
            .join(ResearchPaper, ResearchPaper.id == L.research_paper_id)
            .join(N, N.id == L.knowledge_node_id)
            .where(*where)
            .order_by(L.created_at.desc(), L.id)
            .limit(limit)
            .offset(offset)
        )
        return [(r[0], r[1], r[2], r[3]) for r in rows.all()], total

    async def for_paper(
        self, user_id: uuid.UUID, paper_id: uuid.UUID
    ) -> list[tuple[L, str, str, str]]:
        rows = await self._db.execute(
            select(L, ResearchPaper.title, N.name, N.node_type)
            .join(ResearchPaper, ResearchPaper.id == L.research_paper_id)
            .join(N, N.id == L.knowledge_node_id)
            .where(
                L.user_id == user_id, L.research_paper_id == paper_id, L.link_status != "rejected"
            )
            .order_by(N.name)
        )
        return [(r[0], r[1], r[2], r[3]) for r in rows.all()]

    async def for_node(self, user_id: uuid.UUID, node_id: uuid.UUID) -> list[tuple[L, str, str]]:
        """(link, paper title, project title) for a concept, suggested and confirmed."""
        rows = await self._db.execute(
            select(L, ResearchPaper.title, ResearchProject.title)
            .join(ResearchPaper, ResearchPaper.id == L.research_paper_id)
            .join(ResearchProject, ResearchProject.id == L.research_project_id)
            .where(
                L.user_id == user_id,
                L.knowledge_node_id == node_id,
                L.link_status != "rejected",
                ResearchPaper.archived_at.is_(None),
            )
            .order_by(L.link_status.desc(), ResearchPaper.title)
            .limit(100)
        )
        return [(r[0], r[1], r[2]) for r in rows.all()]

    async def gaps_for_papers(
        self, user_id: uuid.UUID, paper_ids: Sequence[uuid.UUID]
    ) -> list[ResearchGap]:
        if not paper_ids:
            return []
        rows = await self._db.execute(
            select(ResearchGap)
            .join(ResearchGapEvidence, ResearchGapEvidence.gap_id == ResearchGap.id)
            .where(
                ResearchGap.user_id == user_id,
                ResearchGapEvidence.research_paper_id.in_(paper_ids),
                ResearchGapEvidence.evidence_role == "supporting",
                ResearchGap.validation_status != "rejected",
            )
            .distinct()
            .order_by(ResearchGap.title)
            .limit(20)
        )
        return list(rows.scalars())
