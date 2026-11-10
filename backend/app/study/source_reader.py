"""SourceReader: the one way generators read study material (D-79).

It never rebuilds ingestion or retrieval: it resolves ids through `ScopeResolver` (the only source
of a verified document set, completed active versions only) and reads chunks with owner-scoped
queries. Three read modes:

* ordered   - every chunk in reading order (document name, then chunk index). For summaries and
              study guides. If the scope does not fit the budget the caller picks batches
              (`ordered_batches`, for map-reduce) or sampling.
* sampled   - evenly spaced chunks across the whole scope until the budget is used, so every part
              of a large scope is represented and the first pages are not the only ones read.
* retrieved - the best chunks for a query, via the Phase 3 hybrid `Searcher`.

Text is returned to the engine only; it is never logged and never stored again (D-82).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Literal

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.repositories.study_source_repository import (
    ChunkRow,
    Placement,
    StudySourceRepository,
)
from app.repositories.workspace_repository import WorkspaceRepository
from app.retrieval.scope import ResolvedScope, ScopeResolver
from app.retrieval.searcher import QueryEmbedder, Searcher
from app.study.errors import NoSourcesError, SourceTooLargeError
from app.study.schemas import SourceSpec

ReadMode = Literal["ordered", "sampled", "retrieved", "text"]
CHARS_PER_TOKEN = 3
FETCH_BATCH = 200


def estimate_tokens(text: str) -> int:
    return -(-len(text) // CHARS_PER_TOKEN)


@dataclass(frozen=True)
class SourceUnit:
    """One passage with its provenance. `chunk_id` is None for a pasted text passage."""

    chunk_id: uuid.UUID | None
    document_id: uuid.UUID | None
    document_name: str
    chunk_index: int
    content: str
    page_number: int | None
    slide_number: int | None
    section_heading: str | None
    tokens: int


@dataclass(frozen=True)
class ResolvedSource:
    """A verified source: the owner, the documents (or pasted text) and where the result lives."""

    user_id: uuid.UUID
    scope: ResolvedScope | None
    text: str | None
    workspace_id: uuid.UUID
    subject_id: uuid.UUID | None
    chapter_id: uuid.UUID | None

    @property
    def document_ids(self) -> tuple[uuid.UUID, ...]:
        return self.scope.document_ids if self.scope else ()


@dataclass(frozen=True)
class SourceEstimate:
    units: int
    tokens: int
    documents: int


@dataclass(frozen=True)
class SourceBundle:
    units: tuple[SourceUnit, ...]
    mode: ReadMode
    units_available: int
    tokens_available: int

    @property
    def tokens(self) -> int:
        return sum(u.tokens for u in self.units)

    @property
    def truncated(self) -> bool:
        return len(self.units) < self.units_available

    def stats(self) -> dict[str, object]:
        """Counts only: safe to store and to return (no text)."""
        return {
            "mode": self.mode,
            "units_available": self.units_available,
            "units_included": len(self.units),
            "tokens_included": self.tokens,
            "tokens_available": self.tokens_available,
            "truncated": self.truncated,
        }


def _unit(row: ChunkRow) -> SourceUnit:
    return SourceUnit(
        chunk_id=row.chunk_id,
        document_id=row.document_id,
        document_name=row.document_name,
        chunk_index=row.chunk_index,
        content=row.content,
        page_number=row.page_number,
        slide_number=row.slide_number,
        section_heading=row.section_heading,
        tokens=row.token_count or estimate_tokens(row.content),
    )


def pick_evenly(sizes: Sequence[int], budget: int) -> list[int]:
    """Indexes of items chosen at an even stride so the whole range is covered within `budget`.

    Greedy over a fixed stride: first work out how many items fit (by average size), then take
    that many evenly spaced indexes and drop ones that overflow. Deterministic, order-preserving.
    """
    n = len(sizes)
    if n == 0 or budget <= 0:
        return []
    if sum(sizes) <= budget:
        return list(range(n))
    average = max(1, sum(sizes) // n)
    target = max(1, min(n, budget // average))
    picked = sorted({(i * n) // target for i in range(target)})
    spent = 0
    chosen: list[int] = []
    for idx in picked:
        if chosen and spent + sizes[idx] > budget:
            continue
        chosen.append(idx)
        spent += sizes[idx]
    return chosen


class SourceReader:
    def __init__(
        self,
        db: AsyncSession,
        settings: Settings,
        embedder: QueryEmbedder | None = None,
    ) -> None:
        self._db = db
        self._s = settings
        self._repo = StudySourceRepository(db)
        self._embedder = embedder

    # resolve ─────────────────────────────────────────────────────────────────

    async def resolve(self, user_id: uuid.UUID, spec: SourceSpec) -> ResolvedSource:
        """Verify the source belongs to `user_id`. 404 for anything that is not theirs;
        NoSourcesError when it is theirs but nothing in it is ready to read."""
        if spec.type == "text":
            assert spec.text is not None and spec.workspace_id is not None
            if await WorkspaceRepository(self._db).get_for_user(spec.workspace_id, user_id) is None:
                raise HTTPException(
                    404, detail={"code": "RESOURCE_NOT_FOUND", "message": "Scope not found."}
                )  # the same 404 as any foreign id
            if len(spec.text) > self._s.study_max_text_source_chars:
                raise SourceTooLargeError()
            return ResolvedSource(user_id, None, spec.text, spec.workspace_id, None, None)

        resolver = ScopeResolver(self._db)
        if spec.type == "documents":
            assert spec.ids
            scope = await resolver.resolve_documents(user_id, spec.ids)
        else:
            scope = await resolver.resolve(user_id, spec.type, spec.id)
        if not scope.document_ids:
            raise NoSourcesError()
        if len(scope.document_ids) > self._s.study_max_sources_per_request:
            raise SourceTooLargeError()

        placements = await self._repo.placements(user_id, scope.document_ids)
        if not placements:
            raise NoSourcesError()
        workspace_id, subject_id, chapter_id = _common_placement(placements)
        if spec.type == "subject" and spec.id is not None:
            subject_id = spec.id
        if spec.type == "chapter" and spec.id is not None:
            chapter_id = spec.id
        if chapter_id is not None and subject_id is None:
            subject_id = _first_subject(placements)
        return ResolvedSource(user_id, scope, None, workspace_id, subject_id, chapter_id)

    # estimate ────────────────────────────────────────────────────────────────

    async def estimate(self, source: ResolvedSource) -> SourceEstimate:
        if source.text is not None:
            return SourceEstimate(1, estimate_tokens(source.text), 0)
        index = await self._repo.chunk_index(
            source.user_id, source.document_ids, self._s.embedding_index_version
        )
        if not index:
            raise NoSourcesError()
        return SourceEstimate(len(index), sum(t for _, t in index), len(source.document_ids))

    # read modes ──────────────────────────────────────────────────────────────

    def _text_bundle(self, source: ResolvedSource) -> SourceBundle:
        assert source.text is not None
        unit = SourceUnit(
            None,
            None,
            "Pasted text",
            0,
            source.text,
            None,
            None,
            None,
            estimate_tokens(source.text),
        )
        return SourceBundle((unit,), "text", 1, unit.tokens)

    async def _fetch(self, source: ResolvedSource, ids: Sequence[uuid.UUID]) -> list[SourceUnit]:
        units: list[SourceUnit] = []
        for start in range(0, len(ids), FETCH_BATCH):
            rows = await self._repo.chunks_by_ids(
                source.user_id,
                source.document_ids,
                ids[start : start + FETCH_BATCH],
                self._s.embedding_index_version,
            )
            units.extend(_unit(r) for r in rows)
        return units

    async def read_ordered(self, source: ResolvedSource, max_tokens: int) -> SourceBundle:
        """Everything, in order. SourceTooLargeError if it does not fit: the caller then chooses
        `ordered_batches` (map-reduce) or `read_sampled`, never a silent cut."""
        if source.text is not None:
            return self._text_bundle(source)
        index = await self._repo.chunk_index(
            source.user_id, source.document_ids, self._s.embedding_index_version
        )
        if not index:
            raise NoSourcesError()
        total = sum(t for _, t in index)
        if total > max_tokens:
            raise SourceTooLargeError()
        units = await self._fetch(source, [cid for cid, _ in index])
        return SourceBundle(tuple(units), "ordered", len(index), total)

    async def ordered_batches(
        self, source: ResolvedSource, batch_tokens: int
    ) -> list[SourceBundle]:
        """The whole scope in reading order, split into consecutive batches of at most
        `batch_tokens` (a single oversized chunk gets its own batch). Concatenating the batches
        gives every chunk exactly once, which is what makes map-reduce coverage checkable (M1)."""
        if source.text is not None:
            return [self._text_bundle(source)]
        index = await self._repo.chunk_index(
            source.user_id, source.document_ids, self._s.embedding_index_version
        )
        if not index:
            raise NoSourcesError()
        if sum(t for _, t in index) > self._s.study_max_scope_tokens:
            raise SourceTooLargeError()
        total_tokens = sum(t for _, t in index)
        batches: list[SourceBundle] = []
        for ids in _split(index, batch_tokens):
            units = await self._fetch(source, ids)
            batches.append(SourceBundle(tuple(units), "ordered", len(index), total_tokens))
        return batches

    async def read_sampled(self, source: ResolvedSource, max_tokens: int) -> SourceBundle:
        """Evenly spaced chunks across the scope within `max_tokens`. Reports truncation."""
        if source.text is not None:
            return self._text_bundle(source)
        index = await self._repo.chunk_index(
            source.user_id, source.document_ids, self._s.embedding_index_version
        )
        if not index:
            raise NoSourcesError()
        chosen = pick_evenly([t for _, t in index], max_tokens)
        units = await self._fetch(source, [index[i][0] for i in chosen])
        return SourceBundle(tuple(units), "sampled", len(index), sum(t for _, t in index))

    async def read_retrieved(
        self, source: ResolvedSource, query: str, max_tokens: int, top_k: int = 20
    ) -> SourceBundle:
        """The best passages for `query` (hybrid search, falls back to keyword). Returned in
        reading order so the prompt stays coherent."""
        if source.text is not None:
            return self._text_bundle(source)
        assert source.scope is not None
        result = await Searcher(self._db, self._s, self._embedder).search(
            source.scope, query, top_k=top_k, token_budget=max_tokens
        )
        if not result.hits:
            raise NoSourcesError()
        rows = [
            ChunkRow(
                h.chunk_id,
                h.document_id,
                h.document_name,
                h.chunk_index,
                h.content,
                h.page_number,
                h.slide_number,
                h.section_heading,
                h.token_count,
            )
            for h in sorted(result.hits, key=lambda h: (h.document_name, h.chunk_index))
        ]
        index = await self._repo.chunk_index(
            source.user_id, source.document_ids, self._s.embedding_index_version
        )
        return SourceBundle(
            tuple(_unit(r) for r in rows), "retrieved", len(index), sum(t for _, t in index)
        )


def _split(index: Sequence[tuple[uuid.UUID, int]], batch_tokens: int) -> Iterator[list[uuid.UUID]]:
    current: list[uuid.UUID] = []
    spent = 0
    for chunk_id, tokens in index:
        if current and spent + tokens > batch_tokens:
            yield current
            current, spent = [], 0
        current.append(chunk_id)
        spent += tokens
    if current:
        yield current


def _common_placement(
    placements: Sequence[Placement],
) -> tuple[uuid.UUID, uuid.UUID | None, uuid.UUID | None]:
    first = placements[0]
    subject = (
        first.subject_id if all(p.subject_id == first.subject_id for p in placements) else None
    )
    chapter = (
        first.chapter_id if all(p.chapter_id == first.chapter_id for p in placements) else None
    )
    return first.workspace_id, subject, chapter


def _first_subject(placements: Sequence[Placement]) -> uuid.UUID | None:
    return next((p.subject_id for p in placements if p.subject_id), None)
