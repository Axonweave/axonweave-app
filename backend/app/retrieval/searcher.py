"""Keyword, semantic and hybrid search (D-73). Hybrid = vector + full-text fused with RRF; no
reranker. Queries and chunk text are never logged."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal, Protocol

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.embeddings.errors import EmbeddingError, EmbeddingNotConfiguredError
from app.repositories.retrieval_repository import ChunkHit, RetrievalRepository
from app.retrieval.scope import ResolvedScope

logger = structlog.get_logger(__name__)
Mode = Literal["keyword", "semantic", "hybrid"]
CHARS_PER_TOKEN = 3


class QueryEmbedder(Protocol):
    async def embed_query(self, user_id: uuid.UUID, text: str) -> tuple[list[float], str]: ...


@dataclass(frozen=True)
class SearchResult:
    hits: list[ChunkHit]
    mode_used: Mode  # becomes "keyword" when the embedder is unavailable
    degraded: bool


def rrf_fuse(lists: list[list[ChunkHit]], k: int) -> list[ChunkHit]:
    scores: dict[uuid.UUID, float] = {}
    first: dict[uuid.UUID, ChunkHit] = {}
    for hits in lists:
        for rank, hit in enumerate(hits, start=1):
            scores[hit.chunk_id] = scores.get(hit.chunk_id, 0.0) + 1.0 / (k + rank)
            first.setdefault(hit.chunk_id, hit)
    ordered = sorted(scores, key=lambda cid: (-scores[cid], str(cid)))
    return [first[cid] for cid in ordered]


class Searcher:
    def __init__(
        self, db: AsyncSession, settings: Settings, embedder: QueryEmbedder | None
    ) -> None:
        self._repo = RetrievalRepository(db)
        self._s = settings
        self._embedder = embedder

    async def search(
        self,
        scope: ResolvedScope,
        query: str,
        *,
        mode: Mode = "hybrid",
        top_k: int | None = None,
        token_budget: int | None = None,
    ) -> SearchResult:
        s = self._s
        top_k = top_k or s.retrieval_top_k
        budget = token_budget or s.retrieval_context_token_budget
        cands = s.retrieval_candidates
        ids, uid, iv = scope.document_ids, scope.user_id, s.embedding_index_version

        vector_hits: list[ChunkHit] = []
        degraded = False
        used: Mode = mode
        if mode in ("semantic", "hybrid"):
            try:
                if self._embedder is None:
                    raise EmbeddingNotConfiguredError()
                vec, model = await self._embedder.embed_query(uid, query)
                found = await self._repo.vector_search(
                    uid, ids, vec, model=model, index_version=iv, limit=cands
                )
                vector_hits = [h for h in found if h.score >= s.retrieval_min_vector_score]
            except EmbeddingError as exc:
                logger.warning("search_embedding_unavailable", error_code=exc.code)
                degraded = True
                used = "keyword"
        keyword_hits: list[ChunkHit] = []
        if used in ("keyword", "hybrid"):
            keyword_hits = await self._repo.keyword_search(
                uid, ids, query, index_version=iv, limit=cands
            )

        if used == "semantic":
            ranked = vector_hits
        elif used == "keyword":
            ranked = keyword_hits
        else:
            ranked = rrf_fuse([vector_hits, keyword_hits], s.retrieval_rrf_k)

        chosen: list[ChunkHit] = []
        spent = 0
        for hit in ranked:
            cost = hit.token_count or -(-len(hit.content) // CHARS_PER_TOKEN)
            if chosen and spent + cost > budget:
                break
            chosen.append(hit)
            spent += cost
            if len(chosen) >= top_k:
                break
        logger.info("search_done", mode=used, degraded=degraded, results=len(chosen), docs=len(ids))
        return SearchResult(hits=chosen, mode_used=used, degraded=degraded)
