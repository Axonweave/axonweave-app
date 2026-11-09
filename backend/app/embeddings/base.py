"""The embedding provider interface (D-69)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal, Self

from app.core.config import Settings

Task = Literal["document", "query"]


@dataclass(frozen=True)
class EmbeddingResult:
    vectors: list[list[float]]
    model: str  # the provider's own model id, as stored with each vector
    input_tokens: int | None = None  # provider-reported; None when unknown (never 0)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EmbeddingModelInfo:
    provider_model_id: str
    display_name: str | None
    supported_methods: tuple[str, ...]
    input_token_limit: int | None


class EmbeddingProvider(ABC):
    name: str
    display_name: str
    kind: Literal["real", "test"] = "real"

    @classmethod
    @abstractmethod
    def create(cls, settings: Settings) -> Self: ...

    @abstractmethod
    async def embed(
        self, texts: list[str], *, task: Task, model: str, dimensions: int, timeout: float
    ) -> EmbeddingResult:
        """One vector per text, in order. No retries here (D-69): the caller owns them."""

    async def list_models(self) -> list[EmbeddingModelInfo]:
        return []

    async def aclose(self) -> None:
        return None
