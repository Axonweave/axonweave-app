"""Embedding stage and EmbeddingService (D-69): batching, retries, quota, usage, failures."""

import uuid
from typing import Any

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.database.vector import EMBEDDING_COLUMN_DIMENSIONS
from app.embeddings.base import EmbeddingProvider, EmbeddingResult
from app.embeddings.errors import (
    EmbeddingAuthFailedError,
    EmbeddingDimensionMismatchError,
    EmbeddingQuotaExceededError,
    EmbeddingRateLimitedError,
)
from app.embeddings.fake_provider import FAKE_MODEL, FakeEmbeddingProvider, _vector
from app.embeddings.service import EmbeddingService
from app.ingestion import pipeline
from app.models.ai_usage_record import AiUsageRecord
from tests.conftest import _TestSessionLocal
from tests.ingestion import fixtures as fx
from tests.ingestion.test_pipeline import Env, env  # noqa: F401  (fixture)

DIM = EMBEDDING_COLUMN_DIMENSIONS


class ScriptedProvider(EmbeddingProvider):
    """Raises the scripted errors first, then answers like the fake provider."""

    name = "scripted"
    display_name = "Scripted"

    def __init__(self, errors: list[Exception] | None = None, dims: int = DIM) -> None:
        self.errors = list(errors or [])
        self.dims = dims
        self.calls = 0
        self.batch_sizes: list[int] = []

    @classmethod
    def create(cls, settings: Any) -> "ScriptedProvider":
        return cls()

    async def embed(
        self, texts: list[str], *, task: Any, model: str, dimensions: int, timeout: float
    ) -> EmbeddingResult:
        self.calls += 1
        self.batch_sizes.append(len(texts))
        if self.errors:
            raise self.errors.pop(0)
        return EmbeddingResult(vectors=[_vector(t, self.dims) for t in texts], model=FAKE_MODEL)

    async def list_models(self) -> list[Any]:
        return []

    async def aclose(self) -> None:
        return None


async def no_sleep(_: float) -> None:
    return None


def service(provider: EmbeddingProvider, **changes: Any) -> EmbeddingService:
    settings = get_settings().model_copy(update=changes)
    return EmbeddingService(_TestSessionLocal, provider, settings, sleep=no_sleep)


async def usage_rows() -> list[AiUsageRecord]:
    async with _TestSessionLocal() as db:
        return list((await db.execute(select(AiUsageRecord))).scalars())


class TestService:
    async def test_batches_and_records_usage(self, env: Env):  # noqa: F811
        provider = ScriptedProvider()
        svc = service(provider, embedding_batch_size=2)
        vectors, model = await svc.embed_documents(env.user.id, ["a b", "c d", "e f", "g h", "i j"])
        assert len(vectors) == 5 and model == FAKE_MODEL
        assert provider.batch_sizes == [2, 2, 1]
        rows = await usage_rows()
        assert len(rows) == 3
        assert all(r.request_kind == "embedding" and r.user_id == env.user.id for r in rows)
        assert all(r.estimated_cost is None and r.input_tokens for r in rows)

    async def test_transient_errors_are_retried(self, env: Env):  # noqa: F811
        provider = ScriptedProvider([EmbeddingRateLimitedError(), EmbeddingRateLimitedError()])
        vectors, _ = await service(provider).embed_documents(env.user.id, ["x y"])
        assert len(vectors) == 1 and provider.calls == 3
        statuses = [r.request_status for r in await usage_rows()]
        assert statuses.count("failed") == 2 and statuses.count("success") == 1

    async def test_retries_are_bounded(self, env: Env):  # noqa: F811
        provider = ScriptedProvider([EmbeddingRateLimitedError()] * 10)
        with pytest.raises(EmbeddingRateLimitedError):
            await service(provider, embedding_max_retries=2).embed_documents(env.user.id, ["x"])
        assert provider.calls == 3

    async def test_permanent_errors_are_not_retried(self, env: Env):  # noqa: F811
        provider = ScriptedProvider([EmbeddingAuthFailedError()])
        with pytest.raises(EmbeddingAuthFailedError):
            await service(provider).embed_documents(env.user.id, ["x"])
        assert provider.calls == 1

    async def test_wrong_dimension_is_rejected(self, env: Env):  # noqa: F811
        with pytest.raises(EmbeddingDimensionMismatchError):
            await service(ScriptedProvider(dims=DIM - 1)).embed_documents(env.user.id, ["x"])

    async def test_daily_token_quota(self, env: Env):  # noqa: F811
        svc = service(ScriptedProvider(), ai_daily_token_quota=1)
        await svc.embed_documents(env.user.id, ["one two three four five six"])
        with pytest.raises(EmbeddingQuotaExceededError):
            await svc.embed_documents(env.user.id, ["again"])


class TestPipelineStage:
    async def run(self, env: Env, provider: EmbeddingProvider) -> tuple[str, dict[str, Any]]:  # noqa: F811
        text = "\n\n".join(fx.paragraph(i) for i in range(8)).encode()
        document_id, job_id = await env.add("txt", text)
        deps = env.deps()
        deps.embedder = service(provider)
        outcome = await pipeline.run_job(deps, job_id)
        return outcome, await env.snapshot(document_id)

    async def test_chunks_get_vectors_and_model(self, env: Env):  # noqa: F811
        outcome, snap = await self.run(env, FakeEmbeddingProvider.create(get_settings()))
        assert outcome == pipeline.SUCCEEDED
        chunks = snap["chunks"]
        assert chunks and all(c.embedding is not None for c in chunks)
        assert all(
            c.embedding_model == FAKE_MODEL and c.embedding_dimensions == DIM for c in chunks
        )
        assert "EMBEDDINGS_UNAVAILABLE" not in snap["version"].warnings

    async def test_without_embedder_completes_with_warning(self, env: Env):  # noqa: F811
        document_id, job_id = await env.add("txt", fx.paragraph(0).encode())
        assert await pipeline.run_job(env.deps(), job_id) == pipeline.SUCCEEDED
        snap = await env.snapshot(document_id)
        assert "EMBEDDINGS_UNAVAILABLE" in snap["version"].warnings
        assert all(c.embedding is None for c in snap["chunks"])

    async def test_permanent_embedding_failure_fails_job_with_code(self, env: Env):  # noqa: F811
        outcome, snap = await self.run(env, ScriptedProvider([EmbeddingAuthFailedError()]))
        assert outcome == pipeline.FAILED
        assert snap["jobs"][0].error_code == "EMBEDDING_AUTH_FAILED"
        assert snap["chunks"] == [] and snap["doc"].processing_status == "failed"

    async def test_transient_embedding_failure_requeues(self, env: Env):  # noqa: F811
        provider = ScriptedProvider([EmbeddingRateLimitedError()] * 10)
        text = fx.paragraph(0).encode()
        _, job_id = await env.add("txt", text)
        deps = env.deps(embedding_max_retries=0)
        deps.embedder = service(provider, embedding_max_retries=0)
        assert await pipeline.run_job(deps, job_id) == pipeline.RETRY
        assert uuid.UUID(str(job_id))
