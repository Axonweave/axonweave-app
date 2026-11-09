"""Embedding orchestration: batching, retries, quota, usage rows (D-69).

Adapters do no retries; this layer owns them. Every provider call writes one `ai_usage_records` row
with `request_kind = 'embedding'`: provider-reported tokens when the provider says them, otherwise
an estimate marked as such, and NULL cost because no price is verified (D-39). Texts are never
logged: only counts, ids, codes and timings.
"""

from __future__ import annotations

import asyncio
import random
import time
import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.embeddings.base import EmbeddingProvider, EmbeddingResult, Task
from app.embeddings.errors import (
    EmbeddingDimensionMismatchError,
    EmbeddingError,
    EmbeddingQuotaExceededError,
)
from app.repositories.ai_catalog_repository import AiCatalogRepository
from app.repositories.ai_usage_repository import AiUsageRepository

logger = structlog.get_logger(__name__)

CHARS_PER_TOKEN = 3  # the same conservative estimate the context manager uses (D-47)


def estimate_tokens(texts: list[str]) -> int:
    return sum(-(-len(t) // CHARS_PER_TOKEN) for t in texts)


class EmbeddingService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        provider: EmbeddingProvider,
        settings: Settings,
        *,
        sleep: object = None,
    ) -> None:
        self._factory = session_factory
        self._provider = provider
        self._settings = settings
        self._sleep = sleep or asyncio.sleep  # tests pass a no-op to skip backoff
        self._model_row: tuple[uuid.UUID, uuid.UUID] | None = None  # (provider_id, model_id)

    @property
    def kind(self) -> str:
        return self._provider.kind

    # ── public API ───────────────────────────────────────────────────────────

    async def embed_documents(
        self, user_id: uuid.UUID, texts: list[str]
    ) -> tuple[list[list[float]], str]:
        result = await self._embed(user_id, texts, "document")
        return result.vectors, result.model

    async def embed_query(self, user_id: uuid.UUID, text: str) -> tuple[list[float], str]:
        result = await self._embed(user_id, [text], "query")
        return result.vectors[0], result.model

    # ── internals ────────────────────────────────────────────────────────────

    async def _embed(self, user_id: uuid.UUID, texts: list[str], task: Task) -> EmbeddingResult:
        s = self._settings
        async with self._factory() as db:
            used = await AiUsageRepository(db).tokens_today(user_id)
        if used >= s.ai_daily_token_quota:
            raise EmbeddingQuotaExceededError()

        vectors: list[list[float]] = []
        model = s.embedding_model
        for start in range(0, len(texts), s.embedding_batch_size):
            batch = texts[start : start + s.embedding_batch_size]
            result = await self._embed_batch(user_id, batch, task)
            vectors.extend(result.vectors)
            model = result.model
        return EmbeddingResult(vectors=vectors, model=model)

    async def _embed_batch(
        self, user_id: uuid.UUID, batch: list[str], task: Task
    ) -> EmbeddingResult:
        s = self._settings
        attempt = 0
        while True:
            started = time.monotonic()
            try:
                result = await self._provider.embed(
                    batch,
                    task=task,
                    model=s.embedding_model,
                    dimensions=s.embedding_dimensions,
                    timeout=s.embedding_timeout_seconds,
                )
                if len(result.vectors) != len(batch) or any(
                    len(v) != s.embedding_dimensions for v in result.vectors
                ):
                    raise EmbeddingDimensionMismatchError()
            except EmbeddingError as exc:
                await self._record(user_id, batch, None, started, error=exc.code)
                if exc.transient and attempt < s.embedding_max_retries:
                    attempt += 1
                    delay = min(2**attempt, 20) + random.uniform(0, 0.5)  # noqa: S311
                    logger.warning("embedding_retry", attempt=attempt, error_code=exc.code)
                    await self._sleep(delay)  # type: ignore[operator]
                    continue
                raise
            await self._record(user_id, batch, result, started, error=None)
            return result

    async def _catalog_ids(self, db: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
        """Usage rows reference the model catalog. Embedding models are listed there but never
        enabled, so they cannot show up as a chat model."""
        if self._model_row is None:
            catalog = AiCatalogRepository(db)
            provider = await catalog.upsert_provider(
                self._provider.name, self._provider.display_name
            )
            model = await catalog.upsert_model(
                provider.id,
                f"embedding:{self._provider.name}:{self._settings.embedding_model}",
                {
                    "provider_model_id": self._settings.embedding_model or "fake-embedding",
                    "display_name": f"{self._provider.display_name} (embeddings)",
                    "is_enabled": False,
                    "is_default": False,
                    "capabilities": {"kind": "embedding"},
                },
            )
            self._model_row = (provider.id, model.id)
        return self._model_row

    async def _record(
        self,
        user_id: uuid.UUID,
        batch: list[str],
        result: EmbeddingResult | None,
        started: float,
        *,
        error: str | None,
    ) -> None:
        reported = result.input_tokens if result is not None else None
        try:
            async with self._factory() as db:
                provider_id, model_id = await self._catalog_ids(db)
                await AiUsageRepository(db).add(
                    user_id=user_id,
                    provider_id=provider_id,
                    model_id=model_id,
                    input_tokens=reported if reported is not None else estimate_tokens(batch),
                    output_tokens=None,
                    usage_source="provider_reported" if reported is not None else "estimated",
                    estimated_cost=None,  # no verified price: unknown is NULL, not 0 (D-39)
                    currency=None,
                    pricing_version=None,
                    request_kind="embedding",
                    request_status="failed" if error else "success",
                    error_code=error,
                    duration_ms=int((time.monotonic() - started) * 1000),
                )
                await db.commit()
        except Exception as exc:  # accounting must never break the embedding itself
            self._model_row = None
            logger.error("embedding_usage_record_failed", error_type=type(exc).__name__)
