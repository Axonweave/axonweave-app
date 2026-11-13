"""Graph reads, edits and traversal (Phase 6 M6.3). Every query is filtered by `user_id` (rule 3);
nothing is fetched by id alone and checked later. Traversal is breadth-first with one batched query
per level, a depth cap and a node cap, so a graph can never be expanded without bound (spec 11.3).
SQL stays here (route -> service -> repository)."""

from __future__ import annotations

import uuid
from collections.abc import Collection, Sequence
from typing import Any

from sqlalchemy import and_, delete, func, literal, or_, select, union_all, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.knowledge import (
    KnowledgeDuplicateCandidate,
    KnowledgeEdge,
    KnowledgeEvidence,
    KnowledgeMergeHistory,
    KnowledgeNode,
    KnowledgeNodeAlias,
)

NODE_SORTS = {
    "name": KnowledgeNode.normalised_name,
    "created_at": KnowledgeNode.created_at,
    "updated_at": KnowledgeNode.updated_at,
}
EDGE_ENDS = ("source", "target")


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class KnowledgeGraphRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # nodes ───────────────────────────────────────────────────────────────────

    async def get_node(
        self, user_id: uuid.UUID, node_id: uuid.UUID, *, include_archived: bool = False
    ) -> KnowledgeNode | None:
        stmt = select(KnowledgeNode).where(
            KnowledgeNode.id == node_id, KnowledgeNode.user_id == user_id
        )
        if not include_archived:
            stmt = stmt.where(KnowledgeNode.archived_at.is_(None))
        return (await self._db.execute(stmt)).scalar_one_or_none()

    async def get_nodes(
        self, user_id: uuid.UUID, node_ids: Collection[uuid.UUID]
    ) -> list[KnowledgeNode]:
        if not node_ids:
            return []
        rows = await self._db.execute(
            select(KnowledgeNode).where(
                KnowledgeNode.user_id == user_id,
                KnowledgeNode.id.in_(list(node_ids)),
                KnowledgeNode.archived_at.is_(None),
            )
        )
        return list(rows.scalars())

    def _node_filters(
        self,
        user_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID | None,
        subject_id: uuid.UUID | None,
        node_type: str | None,
        q: str | None,
        archived: bool,
    ) -> list[Any]:
        conds: list[Any] = [KnowledgeNode.user_id == user_id]
        conds.append(
            KnowledgeNode.archived_at.is_not(None)
            if archived
            else KnowledgeNode.archived_at.is_(None)
        )
        if workspace_id:
            conds.append(KnowledgeNode.workspace_id == workspace_id)
        if subject_id:
            conds.append(KnowledgeNode.subject_id == subject_id)
        if node_type:
            conds.append(KnowledgeNode.node_type == node_type)
        if q:
            like = f"%{_escape_like(q.casefold())}%"
            alias_hit = (
                select(KnowledgeNodeAlias.id)
                .where(
                    KnowledgeNodeAlias.knowledge_node_id == KnowledgeNode.id,
                    KnowledgeNodeAlias.user_id == user_id,
                    KnowledgeNodeAlias.normalised_alias.like(like, escape="\\"),
                )
                .exists()
            )
            conds.append(or_(KnowledgeNode.normalised_name.like(like, escape="\\"), alias_hit))
        return conds

    async def list_nodes(
        self,
        user_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID | None,
        subject_id: uuid.UUID | None,
        node_type: str | None,
        q: str | None,
        archived: bool,
        sort: str,
        descending: bool,
        limit: int,
        offset: int,
    ) -> tuple[list[KnowledgeNode], int]:
        conds = self._node_filters(
            user_id,
            workspace_id=workspace_id,
            subject_id=subject_id,
            node_type=node_type,
            q=q,
            archived=archived,
        )
        total = (
            await self._db.execute(select(func.count(KnowledgeNode.id)).where(*conds))
        ).scalar_one()
        column = NODE_SORTS[sort]
        order = column.desc() if descending else column.asc()
        rows = await self._db.execute(
            select(KnowledgeNode)
            .where(*conds)
            .order_by(order, KnowledgeNode.id)
            .limit(limit)
            .offset(offset)
        )
        return list(rows.scalars()), total

    async def aliases_for(
        self, user_id: uuid.UUID, node_ids: Collection[uuid.UUID]
    ) -> dict[uuid.UUID, list[str]]:
        out: dict[uuid.UUID, list[str]] = {}
        if not node_ids:
            return out
        rows = await self._db.execute(
            select(KnowledgeNodeAlias.knowledge_node_id, KnowledgeNodeAlias.alias)
            .where(
                KnowledgeNodeAlias.user_id == user_id,
                KnowledgeNodeAlias.knowledge_node_id.in_(list(node_ids)),
            )
            .order_by(KnowledgeNodeAlias.normalised_alias)
        )
        for node_id, alias in rows.all():
            out.setdefault(node_id, []).append(alias)
        return out

    async def evidence_counts(
        self, user_id: uuid.UUID, node_ids: Collection[uuid.UUID]
    ) -> dict[uuid.UUID, int]:
        if not node_ids:
            return {}
        rows = await self._db.execute(
            select(KnowledgeEvidence.knowledge_node_id, func.count(KnowledgeEvidence.id))
            .where(
                KnowledgeEvidence.user_id == user_id,
                KnowledgeEvidence.knowledge_node_id.in_(list(node_ids)),
                KnowledgeEvidence.stale.is_(False),
            )
            .group_by(KnowledgeEvidence.knowledge_node_id)
        )
        return {key: count for key, count in rows.all()}  # noqa: C416

    async def degrees(
        self, user_id: uuid.UUID, node_ids: Collection[uuid.UUID]
    ) -> dict[uuid.UUID, int]:
        if not node_ids:
            return {}
        ids = list(node_ids)
        ends = union_all(
            select(KnowledgeEdge.source_node_id.label("node_id")).where(
                KnowledgeEdge.user_id == user_id, KnowledgeEdge.source_node_id.in_(ids)
            ),
            select(KnowledgeEdge.target_node_id.label("node_id")).where(
                KnowledgeEdge.user_id == user_id, KnowledgeEdge.target_node_id.in_(ids)
            ),
        ).subquery()
        rows = await self._db.execute(select(ends.c.node_id, func.count()).group_by(ends.c.node_id))
        return {key: count for key, count in rows.all()}  # noqa: C416

    async def top_nodes_by_degree(
        self,
        user_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID | None,
        subject_id: uuid.UUID | None,
        node_type: str | None,
        q: str | None,
        limit: int,
    ) -> list[KnowledgeNode]:
        """The most connected nodes of a scope: the bounded starting view of the graph."""
        conds = self._node_filters(
            user_id,
            workspace_id=workspace_id,
            subject_id=subject_id,
            node_type=node_type,
            q=q,
            archived=False,
        )
        ends = union_all(
            select(KnowledgeEdge.source_node_id.label("node_id")).where(
                KnowledgeEdge.user_id == user_id
            ),
            select(KnowledgeEdge.target_node_id.label("node_id")).where(
                KnowledgeEdge.user_id == user_id
            ),
        ).subquery()
        degree = (
            select(ends.c.node_id, func.count().label("degree")).group_by(ends.c.node_id).subquery()
        )
        rows = await self._db.execute(
            select(KnowledgeNode)
            .outerjoin(degree, degree.c.node_id == KnowledgeNode.id)
            .where(*conds)
            .order_by(func.coalesce(degree.c.degree, 0).desc(), KnowledgeNode.normalised_name)
            .limit(limit)
        )
        return list(rows.scalars())

    async def count_nodes(
        self, user_id: uuid.UUID, workspace_id: uuid.UUID | None, subject_id: uuid.UUID | None
    ) -> int:
        conds = self._node_filters(
            user_id,
            workspace_id=workspace_id,
            subject_id=subject_id,
            node_type=None,
            q=None,
            archived=False,
        )
        return (
            await self._db.execute(select(func.count(KnowledgeNode.id)).where(*conds))
        ).scalar_one()

    async def type_counts(
        self, user_id: uuid.UUID, workspace_id: uuid.UUID | None, subject_id: uuid.UUID | None
    ) -> dict[str, int]:
        conds = self._node_filters(
            user_id,
            workspace_id=workspace_id,
            subject_id=subject_id,
            node_type=None,
            q=None,
            archived=False,
        )
        rows = await self._db.execute(
            select(KnowledgeNode.node_type, func.count(KnowledgeNode.id))
            .where(*conds)
            .group_by(KnowledgeNode.node_type)
        )
        return {key: count for key, count in rows.all()}  # noqa: C416

    async def count_edges(self, user_id: uuid.UUID, workspace_id: uuid.UUID | None) -> int:
        conds: list[Any] = [KnowledgeEdge.user_id == user_id]
        if workspace_id:
            conds.append(KnowledgeEdge.workspace_id == workspace_id)
        return (
            await self._db.execute(select(func.count(KnowledgeEdge.id)).where(*conds))
        ).scalar_one()

    async def archive_node(self, user_id: uuid.UUID, node_id: uuid.UUID, now: Any) -> None:
        await self._db.execute(
            update(KnowledgeNode)
            .where(KnowledgeNode.id == node_id, KnowledgeNode.user_id == user_id)
            .values(archived_at=now)
        )

    async def delete_node(self, user_id: uuid.UUID, node_id: uuid.UUID) -> None:
        """Permanent. Edges, aliases, evidence and candidates go with it (FK cascade)."""
        await self._db.execute(
            delete(KnowledgeNode).where(
                KnowledgeNode.id == node_id, KnowledgeNode.user_id == user_id
            )
        )

    # aliases ─────────────────────────────────────────────────────────────────

    async def alias_rows(self, user_id: uuid.UUID, node_id: uuid.UUID) -> list[KnowledgeNodeAlias]:
        rows = await self._db.execute(
            select(KnowledgeNodeAlias).where(
                KnowledgeNodeAlias.user_id == user_id,
                KnowledgeNodeAlias.knowledge_node_id == node_id,
            )
        )
        return list(rows.scalars())

    async def delete_alias(self, user_id: uuid.UUID, alias_id: uuid.UUID) -> None:
        await self._db.execute(
            delete(KnowledgeNodeAlias).where(
                KnowledgeNodeAlias.id == alias_id, KnowledgeNodeAlias.user_id == user_id
            )
        )

    # edges ───────────────────────────────────────────────────────────────────

    async def get_edge(self, user_id: uuid.UUID, edge_id: uuid.UUID) -> KnowledgeEdge | None:
        return (
            await self._db.execute(
                select(KnowledgeEdge).where(
                    KnowledgeEdge.id == edge_id, KnowledgeEdge.user_id == user_id
                )
            )
        ).scalar_one_or_none()

    async def delete_edge(self, user_id: uuid.UUID, edge_id: uuid.UUID) -> None:
        await self._db.execute(
            delete(KnowledgeEdge).where(
                KnowledgeEdge.id == edge_id, KnowledgeEdge.user_id == user_id
            )
        )

    async def edges_touching(
        self,
        user_id: uuid.UUID,
        node_ids: Collection[uuid.UUID],
        *,
        types: Sequence[str] | None,
        limit: int,
    ) -> list[KnowledgeEdge]:
        """Edges with either end in `node_ids`, capped. One query per BFS level."""
        if not node_ids:
            return []
        ids = list(node_ids)
        conds: list[Any] = [
            KnowledgeEdge.user_id == user_id,
            or_(KnowledgeEdge.source_node_id.in_(ids), KnowledgeEdge.target_node_id.in_(ids)),
        ]
        if types:
            conds.append(KnowledgeEdge.relationship_type.in_(list(types)))
        rows = await self._db.execute(
            select(KnowledgeEdge)
            .where(*conds)
            .order_by(KnowledgeEdge.created_at, KnowledgeEdge.id)
            .limit(limit)
        )
        return list(rows.scalars())

    async def edges_among(
        self,
        user_id: uuid.UUID,
        node_ids: Collection[uuid.UUID],
        *,
        types: Sequence[str] | None,
        limit: int,
    ) -> list[KnowledgeEdge]:
        """Edges whose BOTH ends are in `node_ids` (the visible subgraph), capped."""
        if len(node_ids) < 2:
            return []
        ids = list(node_ids)
        conds: list[Any] = [
            KnowledgeEdge.user_id == user_id,
            KnowledgeEdge.source_node_id.in_(ids),
            KnowledgeEdge.target_node_id.in_(ids),
        ]
        if types:
            conds.append(KnowledgeEdge.relationship_type.in_(list(types)))
        rows = await self._db.execute(
            select(KnowledgeEdge)
            .where(*conds)
            .order_by(KnowledgeEdge.created_at, KnowledgeEdge.id)
            .limit(limit)
        )
        return list(rows.scalars())

    async def related_nodes(
        self,
        user_id: uuid.UUID,
        node_id: uuid.UUID,
        *,
        relationship_types: Sequence[str],
        as_source: bool,
        limit: int,
    ) -> list[tuple[KnowledgeNode, KnowledgeEdge]]:
        """Nodes on the other end of edges from (`as_source`) or to this node."""
        own, other = (
            (KnowledgeEdge.source_node_id, KnowledgeEdge.target_node_id)
            if as_source
            else (KnowledgeEdge.target_node_id, KnowledgeEdge.source_node_id)
        )
        rows = await self._db.execute(
            select(KnowledgeNode, KnowledgeEdge)
            .join(KnowledgeEdge, other == KnowledgeNode.id)
            .where(
                KnowledgeEdge.user_id == user_id,
                KnowledgeNode.user_id == user_id,
                own == node_id,
                KnowledgeEdge.relationship_type.in_(list(relationship_types)),
                KnowledgeNode.archived_at.is_(None),
            )
            .order_by(KnowledgeNode.normalised_name)
            .limit(limit)
        )
        return [(n, e) for n, e in rows.all()]  # noqa: C416

    # evidence ────────────────────────────────────────────────────────────────

    async def list_evidence(
        self,
        user_id: uuid.UUID,
        *,
        node_id: uuid.UUID | None,
        edge_id: uuid.UUID | None,
        include_stale: bool,
        limit: int,
        offset: int,
    ) -> tuple[list[tuple[KnowledgeEvidence, str]], int]:
        conds: list[Any] = [KnowledgeEvidence.user_id == user_id]
        if node_id:
            conds.append(KnowledgeEvidence.knowledge_node_id == node_id)
        if edge_id:
            conds.append(KnowledgeEvidence.knowledge_edge_id == edge_id)
        if not include_stale:
            conds.append(KnowledgeEvidence.stale.is_(False))
        total = (
            await self._db.execute(select(func.count(KnowledgeEvidence.id)).where(*conds))
        ).scalar_one()
        rows = await self._db.execute(
            select(KnowledgeEvidence, Document.display_name)
            .join(
                Document,
                and_(
                    Document.id == KnowledgeEvidence.document_id,
                    Document.user_id == KnowledgeEvidence.user_id,
                ),
            )
            .where(*conds)
            .order_by(
                KnowledgeEvidence.stale,
                KnowledgeEvidence.confidence.desc().nulls_last(),
                KnowledgeEvidence.created_at,
                KnowledgeEvidence.id,
            )
            .limit(limit)
            .offset(offset)
        )
        return [(ev, name) for ev, name in rows.all()], total  # noqa: C416

    # duplicate candidates ────────────────────────────────────────────────────

    async def get_candidate(
        self, user_id: uuid.UUID, candidate_id: uuid.UUID
    ) -> KnowledgeDuplicateCandidate | None:
        return (
            await self._db.execute(
                select(KnowledgeDuplicateCandidate).where(
                    KnowledgeDuplicateCandidate.id == candidate_id,
                    KnowledgeDuplicateCandidate.user_id == user_id,
                )
            )
        ).scalar_one_or_none()

    async def list_candidates(
        self,
        user_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID | None,
        status: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[KnowledgeDuplicateCandidate], int]:
        conds: list[Any] = [KnowledgeDuplicateCandidate.user_id == user_id]
        if workspace_id:
            conds.append(KnowledgeDuplicateCandidate.workspace_id == workspace_id)
        if status:
            conds.append(KnowledgeDuplicateCandidate.status == status)
        total = (
            await self._db.execute(select(func.count(KnowledgeDuplicateCandidate.id)).where(*conds))
        ).scalar_one()
        rows = await self._db.execute(
            select(KnowledgeDuplicateCandidate)
            .where(*conds)
            .order_by(KnowledgeDuplicateCandidate.created_at, KnowledgeDuplicateCandidate.id)
            .limit(limit)
            .offset(offset)
        )
        return list(rows.scalars()), total

    # merge ───────────────────────────────────────────────────────────────────

    async def edges_of_node(self, user_id: uuid.UUID, node_id: uuid.UUID) -> list[KnowledgeEdge]:
        rows = await self._db.execute(
            select(KnowledgeEdge).where(
                KnowledgeEdge.user_id == user_id,
                or_(
                    KnowledgeEdge.source_node_id == node_id,
                    KnowledgeEdge.target_node_id == node_id,
                ),
            )
        )
        return list(rows.scalars())

    async def move_node_evidence(
        self, user_id: uuid.UUID, from_node: uuid.UUID, to_node: uuid.UUID
    ) -> int:
        """Re-point node evidence at the survivor. Rows that would duplicate evidence the survivor
        already has (same version, passage and type) are dropped first."""
        existing = (
            select(
                KnowledgeEvidence.document_version_id,
                KnowledgeEvidence.chunk_index,
                KnowledgeEvidence.evidence_type,
            )
            .where(
                KnowledgeEvidence.user_id == user_id,
                KnowledgeEvidence.knowledge_node_id == to_node,
                KnowledgeEvidence.knowledge_edge_id.is_(None),
            )
            .subquery()
        )
        await self._db.execute(
            delete(KnowledgeEvidence).where(
                KnowledgeEvidence.user_id == user_id,
                KnowledgeEvidence.knowledge_node_id == from_node,
                KnowledgeEvidence.knowledge_edge_id.is_(None),
                select(literal(1))
                .select_from(existing)
                .where(
                    existing.c.document_version_id == KnowledgeEvidence.document_version_id,
                    existing.c.chunk_index == KnowledgeEvidence.chunk_index,
                    existing.c.evidence_type == KnowledgeEvidence.evidence_type,
                )
                .exists(),
            )
        )
        result = await self._db.execute(
            update(KnowledgeEvidence)
            .where(
                KnowledgeEvidence.user_id == user_id,
                KnowledgeEvidence.knowledge_node_id == from_node,
                KnowledgeEvidence.knowledge_edge_id.is_(None),
            )
            .values(knowledge_node_id=to_node)
        )
        return int(result.rowcount or 0)

    async def move_edge_evidence(
        self, user_id: uuid.UUID, from_edge: uuid.UUID, to_edge: uuid.UUID
    ) -> None:
        existing = (
            select(KnowledgeEvidence.document_version_id, KnowledgeEvidence.chunk_index)
            .where(
                KnowledgeEvidence.user_id == user_id,
                KnowledgeEvidence.knowledge_edge_id == to_edge,
            )
            .subquery()
        )
        await self._db.execute(
            delete(KnowledgeEvidence).where(
                KnowledgeEvidence.user_id == user_id,
                KnowledgeEvidence.knowledge_edge_id == from_edge,
                select(literal(1))
                .select_from(existing)
                .where(
                    existing.c.document_version_id == KnowledgeEvidence.document_version_id,
                    existing.c.chunk_index == KnowledgeEvidence.chunk_index,
                )
                .exists(),
            )
        )
        await self._db.execute(
            update(KnowledgeEvidence)
            .where(
                KnowledgeEvidence.user_id == user_id,
                KnowledgeEvidence.knowledge_edge_id == from_edge,
            )
            .values(knowledge_edge_id=to_edge)
        )

    def add_merge_history(self, **fields: Any) -> KnowledgeMergeHistory:
        row = KnowledgeMergeHistory(**fields)
        self._db.add(row)
        return row
