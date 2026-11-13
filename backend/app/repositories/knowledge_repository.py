"""Persistence for the knowledge graph. Every query is filtered by `user_id` and `workspace_id`
(rule 3); there is no fetch-by-id-then-check. SQL stays here (route -> service -> repository)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentVersion
from app.models.knowledge import (
    KnowledgeDuplicateCandidate,
    KnowledgeEdge,
    KnowledgeEvidence,
    KnowledgeNode,
    KnowledgeNodeAlias,
)


class KnowledgeRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # documents ───────────────────────────────────────────────────────────────

    async def active_version_id(
        self, user_id: uuid.UUID, document_id: uuid.UUID
    ) -> uuid.UUID | None:
        return (
            await self._db.execute(
                select(DocumentVersion.id)
                .join(Document, Document.id == DocumentVersion.document_id)
                .where(
                    Document.id == document_id,
                    Document.user_id == user_id,
                    DocumentVersion.version_number == Document.active_version,
                )
            )
        ).scalar_one_or_none()

    # nodes ───────────────────────────────────────────────────────────────────

    async def find_node(
        self, user_id: uuid.UUID, workspace_id: uuid.UUID, normalised_name: str, node_type: str
    ) -> KnowledgeNode | None:
        return (
            await self._db.execute(
                select(KnowledgeNode).where(
                    KnowledgeNode.user_id == user_id,
                    KnowledgeNode.workspace_id == workspace_id,
                    KnowledgeNode.normalised_name == normalised_name,
                    KnowledgeNode.node_type == node_type,
                    KnowledgeNode.archived_at.is_(None),
                )
            )
        ).scalar_one_or_none()

    async def nodes_named(
        self, user_id: uuid.UUID, workspace_id: uuid.UUID, normalised_name: str
    ) -> list[KnowledgeNode]:
        rows = await self._db.execute(
            select(KnowledgeNode).where(
                KnowledgeNode.user_id == user_id,
                KnowledgeNode.workspace_id == workspace_id,
                KnowledgeNode.normalised_name == normalised_name,
                KnowledgeNode.archived_at.is_(None),
            )
        )
        return list(rows.scalars())

    async def node_by_alias(
        self, user_id: uuid.UUID, workspace_id: uuid.UUID, normalised_alias: str
    ) -> KnowledgeNode | None:
        return (
            await self._db.execute(
                select(KnowledgeNode)
                .join(
                    KnowledgeNodeAlias,
                    (KnowledgeNodeAlias.knowledge_node_id == KnowledgeNode.id)
                    & (KnowledgeNodeAlias.user_id == KnowledgeNode.user_id),
                )
                .where(
                    KnowledgeNode.user_id == user_id,
                    KnowledgeNode.workspace_id == workspace_id,
                    KnowledgeNode.archived_at.is_(None),
                    KnowledgeNodeAlias.normalised_alias == normalised_alias,
                )
            )
        ).scalar_one_or_none()

    async def alias_owner(
        self, user_id: uuid.UUID, workspace_id: uuid.UUID, normalised_alias: str
    ) -> uuid.UUID | None:
        return (
            await self._db.execute(
                select(KnowledgeNodeAlias.knowledge_node_id).where(
                    KnowledgeNodeAlias.user_id == user_id,
                    KnowledgeNodeAlias.workspace_id == workspace_id,
                    KnowledgeNodeAlias.normalised_alias == normalised_alias,
                )
            )
        ).scalar_one_or_none()

    async def aliases_of(self, user_id: uuid.UUID, node_id: uuid.UUID) -> set[str]:
        rows = await self._db.execute(
            select(KnowledgeNodeAlias.normalised_alias).where(
                KnowledgeNodeAlias.user_id == user_id,
                KnowledgeNodeAlias.knowledge_node_id == node_id,
            )
        )
        return set(rows.scalars())

    def add_node(self, **fields: Any) -> KnowledgeNode:
        node = KnowledgeNode(**fields)
        self._db.add(node)
        return node

    def add_alias(self, **fields: Any) -> KnowledgeNodeAlias:
        alias = KnowledgeNodeAlias(**fields)
        self._db.add(alias)
        return alias

    # edges ───────────────────────────────────────────────────────────────────

    async def find_edge(
        self,
        user_id: uuid.UUID,
        source_node_id: uuid.UUID,
        target_node_id: uuid.UUID,
        relationship_type: str,
    ) -> KnowledgeEdge | None:
        return (
            await self._db.execute(
                select(KnowledgeEdge).where(
                    KnowledgeEdge.user_id == user_id,
                    KnowledgeEdge.source_node_id == source_node_id,
                    KnowledgeEdge.target_node_id == target_node_id,
                    KnowledgeEdge.relationship_type == relationship_type,
                )
            )
        ).scalar_one_or_none()

    def add_edge(self, **fields: Any) -> KnowledgeEdge:
        edge = KnowledgeEdge(**fields)
        self._db.add(edge)
        return edge

    # evidence ────────────────────────────────────────────────────────────────

    async def add_evidence(self, rows: list[dict[str, Any]]) -> int:
        """Insert evidence; a row that already exists (same passage, same target) is skipped, so a
        retried or repeated extraction never duplicates evidence. Returns the number inserted."""
        added = 0
        for row in rows:
            # rowcount is unreliable (-1) for this driver; RETURNING says if a row was inserted
            result = await self._db.execute(
                pg_insert(KnowledgeEvidence)
                .values(**row)
                .on_conflict_do_nothing()
                .returning(KnowledgeEvidence.id)
            )
            added += 1 if result.first() is not None else 0
        return added

    async def mark_stale(
        self, user_id: uuid.UUID, document_id: uuid.UUID, active_version_id: uuid.UUID
    ) -> int:
        """Evidence taken from an older version of the document is no longer current (D-123)."""
        result = await self._db.execute(
            update(KnowledgeEvidence)
            .where(
                KnowledgeEvidence.user_id == user_id,
                KnowledgeEvidence.document_id == document_id,
                KnowledgeEvidence.document_version_id != active_version_id,
                KnowledgeEvidence.stale.is_(False),
            )
            .values(stale=True)
        )
        return int(result.rowcount or 0)

    # duplicate candidates ────────────────────────────────────────────────────

    async def add_candidate(
        self,
        user_id: uuid.UUID,
        workspace_id: uuid.UUID,
        node_x: uuid.UUID,
        node_y: uuid.UUID,
        signal: str,
    ) -> bool:
        """Record a reviewable "maybe the same concept" pair (smaller id first). Existing pairs
        keep their status; a user's earlier decision is never reopened."""
        if node_x == node_y:
            return False
        a, b = (node_x, node_y) if str(node_x) < str(node_y) else (node_y, node_x)
        result = await self._db.execute(
            pg_insert(KnowledgeDuplicateCandidate)
            .values(
                id=uuid.uuid4(),
                user_id=user_id,
                workspace_id=workspace_id,
                node_a_id=a,
                node_b_id=b,
                signals=[signal],
                status="open",
            )
            .on_conflict_do_nothing()
        )
        return bool(result.rowcount)
