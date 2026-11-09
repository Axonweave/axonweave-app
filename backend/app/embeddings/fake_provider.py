"""Deterministic embedder for tests and local UI development only (D-69).

Words are hashed into buckets, so texts that share words get similar vectors: enough to test
retrieval ordering without a network. It refuses to run in production and Settings rejects it
there as well."""

from __future__ import annotations

import hashlib
import math
import re
from typing import Self

from app.core.config import AppEnv, Settings
from app.embeddings.base import EmbeddingProvider, EmbeddingResult, Task
from app.embeddings.errors import EmbeddingNotConfiguredError

FAKE_MODEL = "fake-hash-embedding"
_WORD = re.compile(r"[a-z0-9]+")
_STOP = frozenset(
    "a an the of and or to in on is are was were be by for with as at it this that".split()
)


def _vector(text: str, dimensions: int) -> list[float]:
    vec = [0.0] * dimensions
    for word in _WORD.findall(text.lower()):
        if word in _STOP:
            continue
        digest = hashlib.sha256(word.encode()).digest()
        vec[int.from_bytes(digest[:4], "big") % dimensions] += 1.0
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        vec[0] = 1.0
        return vec
    return [v / norm for v in vec]


class FakeEmbeddingProvider(EmbeddingProvider):
    name = "fake"
    display_name = "Fake embedder (test only)"
    kind = "test"

    def __init__(self, app_env: AppEnv) -> None:
        if app_env not in (AppEnv.development, AppEnv.testing):
            raise EmbeddingNotConfiguredError()
        self.calls = 0

    @classmethod
    def create(cls, settings: Settings) -> Self:
        return cls(settings.app_env)

    async def embed(
        self, texts: list[str], *, task: Task, model: str, dimensions: int, timeout: float
    ) -> EmbeddingResult:
        self.calls += 1
        return EmbeddingResult(
            vectors=[_vector(t, dimensions) for t in texts],
            model=FAKE_MODEL,
            input_tokens=sum(len(t) for t in texts) // 3,
        )
