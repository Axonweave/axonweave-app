"""Gemini embedding adapter (official `google-genai` SDK). With `ai/providers/gemini_provider.py`
the ONLY module that imports it (CLAUDE.md rule 13; a test enforces it).

Vendor error text is never returned or logged, only mapped to a code. No retries here (D-69).
"""

from __future__ import annotations

import asyncio
import math
from typing import Any, Self

import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from app.core.config import Settings
from app.embeddings.base import (
    EmbeddingModelInfo,
    EmbeddingProvider,
    EmbeddingResult,
    Task,
)
from app.embeddings.errors import (
    EmbeddingAuthFailedError,
    EmbeddingBadResponseError,
    EmbeddingError,
    EmbeddingInvalidModelError,
    EmbeddingNotConfiguredError,
    EmbeddingRateLimitedError,
    EmbeddingTimeoutError,
    EmbeddingUnavailableError,
)

_TASK_TYPES = {"document": "RETRIEVAL_DOCUMENT", "query": "RETRIEVAL_QUERY"}


def map_error(exc: BaseException) -> EmbeddingError:
    if isinstance(exc, EmbeddingError):
        return exc
    if isinstance(exc, TimeoutError | asyncio.TimeoutError | httpx.TimeoutException):
        return EmbeddingTimeoutError()
    if isinstance(exc, genai_errors.APIError):
        code = getattr(exc, "code", None)
        text = str(getattr(exc, "message", "") or "").lower()
        if code in (401, 403) or "api key" in text:
            return EmbeddingAuthFailedError()
        if code == 404:
            return EmbeddingInvalidModelError()
        if code == 429:
            return EmbeddingRateLimitedError()
        if code == 504:
            return EmbeddingTimeoutError()
        if isinstance(code, int) and code >= 500:
            return EmbeddingUnavailableError()
        return EmbeddingBadResponseError()
    if isinstance(exc, httpx.TransportError | ConnectionError | OSError):
        return EmbeddingUnavailableError()
    return EmbeddingBadResponseError()


def _normalise(vector: list[float]) -> list[float]:
    """Truncated embeddings are not unit length; cosine search wants them to be."""
    norm = math.sqrt(sum(v * v for v in vector))
    return [v / norm for v in vector] if norm else vector


class GeminiEmbeddingProvider(EmbeddingProvider):
    name = "gemini"
    display_name = "Google Gemini embeddings"

    def __init__(self, client: Any) -> None:
        self._client = client

    @classmethod
    def create(cls, settings: Settings) -> Self:
        key = settings.gemini_api_key
        if key is None or not key.get_secret_value().strip():
            raise EmbeddingNotConfiguredError()
        client = genai.Client(
            api_key=key.get_secret_value(),
            http_options=genai_types.HttpOptions(
                async_client_args={
                    "timeout": httpx.Timeout(
                        settings.embedding_timeout_seconds,
                        connect=settings.llm_connect_timeout_seconds,
                    )
                }
            ),
        )
        return cls(client)

    async def embed(
        self, texts: list[str], *, task: Task, model: str, dimensions: int, timeout: float
    ) -> EmbeddingResult:
        if not texts:
            return EmbeddingResult(vectors=[], model=model)
        try:
            response = await asyncio.wait_for(
                self._client.aio.models.embed_content(
                    model=model,
                    contents=texts,
                    config=genai_types.EmbedContentConfig(
                        task_type=_TASK_TYPES[task], output_dimensionality=dimensions
                    ),
                ),
                timeout=timeout,
            )
        except BaseException as exc:
            if isinstance(exc, asyncio.CancelledError | KeyboardInterrupt):
                raise
            raise map_error(exc) from None
        items = getattr(response, "embeddings", None) or []
        if len(items) != len(texts):
            raise EmbeddingBadResponseError()
        vectors: list[list[float]] = []
        for item in items:
            values = getattr(item, "values", None)
            if not values:
                raise EmbeddingBadResponseError()
            vectors.append(_normalise([float(v) for v in values]))
        return EmbeddingResult(vectors=vectors, model=model, input_tokens=None)

    async def list_models(self) -> list[EmbeddingModelInfo]:
        models: list[EmbeddingModelInfo] = []
        try:
            pager = await self._client.aio.models.list()
            async for model in pager:
                methods = tuple(getattr(model, "supported_actions", None) or ())
                if not any("embed" in m.lower() for m in methods):
                    continue
                name = str(getattr(model, "name", "") or "")
                models.append(
                    EmbeddingModelInfo(
                        provider_model_id=name.removeprefix("models/"),
                        display_name=getattr(model, "display_name", None),
                        supported_methods=methods,
                        input_token_limit=getattr(model, "input_token_limit", None),
                    )
                )
        except BaseException as exc:
            if isinstance(exc, asyncio.CancelledError | KeyboardInterrupt):
                raise
            raise map_error(exc) from None
        return models

    async def aclose(self) -> None:
        closer = getattr(getattr(self._client, "aio", None), "aclose", None)
        if closer is not None:
            await closer()
