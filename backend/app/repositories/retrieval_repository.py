"""Owner-scoped SQL for retrieval. Every query filters by user_id and by a document id set that
ScopeResolver verified; nothing here fetches by chunk id alone (CLAUDE.md rule 3)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chapter import Chapter
from app.models.document import Document, DocumentVersion
from app.models.document_chunk import FTS_CONFIG, DocumentChunk
from app.models.folder import Folder
from app.models.subject import Subject
from app.models.workspace import Workspace


@dataclass(frozen=True)
class ChunkHit:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    chunk_index: int
    content: str
    page_number: int | None
    slide_number: int | None
    section_heading: str | None
    token_count: int
    score: float  # vector: cosine similarity; keyword: ts_rank_cd


class RetrievalRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def scope_exists(self, user_id: uuid.UUID, kind: str, scope_id: uuid.UUID) -> bool:
        stmt: Any
        if kind == "workspace":
            stmt = select(Workspace.id).where(
                Workspace.id == scope_id, Workspace.user_id == user_id
            )
        elif kind == "subject":
            stmt = (
                select(Subject.id)
                .join(Workspace, Workspace.id == Subject.workspace_id)
                .where(Subject.id == scope_id, Workspace.user_id == user_id)
            )
        else:
            model: Any = Folder if kind == "folder" else Chapter
            stmt = (
                select(model.id)
                .join(Subject, Subject.id == model.subject_id)
                .join(Workspace, Workspace.id == Subject.workspace_id)
                .where(model.id == scope_id, Workspace.user_id == user_id)
            )
        return (await self.db.execute(stmt.limit(1))).first() is not None

    async def folder_tree_ids(self, user_id: uuid.UUID, folder_id: uuid.UUID) -> list[uuid.UUID]:
        tree = (
            select(Folder.id)
            .join(Subject, Subject.id == Folder.subject_id)
            .join(Workspace, Workspace.id == Subject.workspace_id)
            .where(Folder.id == folder_id, Workspace.user_id == user_id)
            .cte("tree", recursive=True)
        )
        child = select(Folder.id).join(tree, Folder.parent_folder_id == tree.c.id)
        tree = tree.union_all(child)
        return list((await self.db.execute(select(tree.c.id))).scalars())

    async def eligible_document_ids(
        self, user_id: uuid.UUID, kind: str, scope_id: uuid.UUID | None
    ) -> list[uuid.UUID]:
        """Active, completed, non-archived documents of this user inside the scope."""
        stmt = select(Document.id).where(
            Document.user_id == user_id,
            Document.archived_at.is_(None),
            Document.processing_status == "completed",
            Document.active_version.is_not(None),
        )
        if kind == "workspace":
            stmt = stmt.where(Document.workspace_id == scope_id)
        elif kind == "subject":
            stmt = stmt.where(Document.subject_id == scope_id)
        elif kind == "chapter":
            stmt = stmt.where(Document.chapter_id == scope_id)
        elif kind == "document":
            stmt = stmt.where(Document.id == scope_id)
        elif kind == "folder":
            assert scope_id is not None
            tree = await self.folder_tree_ids(user_id, scope_id)
            stmt = stmt.where(Document.folder_id.in_(tree))
        return list((await self.db.execute(stmt)).scalars())

    def _base(self, user_id: uuid.UUID, doc_ids: Sequence[uuid.UUID], index_version: int) -> Any:
        """Only chunks of the active version, current index_version, owned by this user."""
        return (
            select(
                DocumentChunk.id,
                DocumentChunk.document_id,
                Document.display_name,
                DocumentChunk.chunk_index,
                DocumentChunk.content,
                DocumentChunk.page_number,
                DocumentChunk.slide_number,
                DocumentChunk.section_heading,
                DocumentChunk.token_count,
            )
            .join(Document, Document.id == DocumentChunk.document_id)
            .join(
                DocumentVersion,
                (DocumentVersion.id == DocumentChunk.document_version_id)
                & (DocumentVersion.version_number == Document.active_version),
            )
            .where(
                DocumentChunk.user_id == user_id,
                Document.user_id == user_id,
                DocumentChunk.document_id.in_(list(doc_ids)),
                DocumentChunk.index_version == index_version,
            )
        )

    @staticmethod
    def _hits(rows: Any) -> list[ChunkHit]:
        return [ChunkHit(*row) for row in rows]

    async def vector_search(
        self,
        user_id: uuid.UUID,
        doc_ids: Sequence[uuid.UUID],
        vector: list[float],
        *,
        model: str,
        index_version: int,
        limit: int,
    ) -> list[ChunkHit]:
        if not doc_ids:
            return []
        distance = DocumentChunk.embedding.cosine_distance(vector)
        stmt = (
            self._base(user_id, doc_ids, index_version)
            .add_columns((literal(1.0) - distance).label("score"))
            .where(DocumentChunk.embedding.is_not(None), DocumentChunk.embedding_model == model)
            .order_by(distance)  # exact, filtered search (D-73)
            .limit(limit)
        )
        return self._hits((await self.db.execute(stmt)).all())

    async def keyword_search(
        self,
        user_id: uuid.UUID,
        doc_ids: Sequence[uuid.UUID],
        query: str,
        *,
        index_version: int,
        limit: int,
    ) -> list[ChunkHit]:
        if not doc_ids:
            return []
        tsq = func.websearch_to_tsquery(FTS_CONFIG, query)
        score = func.ts_rank_cd(DocumentChunk.content_tsv, tsq).label("score")
        stmt = (
            self._base(user_id, doc_ids, index_version)
            .add_columns(score)
            .where(DocumentChunk.content_tsv.op("@@")(tsq))
            .order_by(score.desc(), DocumentChunk.id)
            .limit(limit)
        )
        return self._hits((await self.db.execute(stmt)).all())

    async def documents_needing_reindex(self, index_version: int, model: str) -> list[uuid.UUID]:
        """Maintenance (not user-scoped by design): documents with stale or missing embeddings."""
        stmt = (
            select(DocumentChunk.document_id)
            .where(
                (DocumentChunk.index_version != index_version)
                | (DocumentChunk.embedding.is_(None))
                | (DocumentChunk.embedding_model != model)
            )
            .distinct()
        )
        return list((await self.db.execute(stmt)).scalars())
