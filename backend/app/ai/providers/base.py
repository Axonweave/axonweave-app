"""The provider contract (AI_ARCHITECTURE.md section 3).

Adapters convert our typed request into a vendor call and normalise the answer. They raise only
`LLMError` subclasses, never retry (the orchestrator does, D-50), enforce the timeouts in the
request, and never return vendor objects. Nothing outside `app/ai/providers/` may import a
vendor SDK.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any, ClassVar, Self

from app.ai.errors import LLMCapabilityError
from app.ai.types import (
    Capabilities,
    LLMRequest,
    LLMResponse,
    ProviderModelInfo,
    StreamEvent,
)
from app.core.config import Settings


class LLMProvider(ABC):
    name: ClassVar[str]
    #: Default capabilities for models of this provider; ModelConfig may refine them.
    capabilities: ClassVar[Capabilities] = Capabilities()
    #: "real" or "test". The API reports it so the UI can badge a test provider (D-60).
    kind: ClassVar[str] = "real"
    display_name: ClassVar[str] = ""

    @classmethod
    @abstractmethod
    def create(cls, settings: Settings) -> Self:
        """Build the adapter from settings; raise LLMNotConfiguredError without credentials."""

    @abstractmethod
    async def generate(self, request: LLMRequest) -> LLMResponse: ...

    @abstractmethod
    def stream(self, request: LLMRequest) -> AsyncIterator[StreamEvent]:
        """Yield zero or more StreamDelta then exactly one StreamEnd.

        If the consumer stops iterating (aclose / cancellation) the adapter must cancel the
        upstream call.
        """

    async def count_tokens(self, request: LLMRequest) -> int | None:
        """Token count for the request, or None if the provider cannot count (capability off)."""
        return None

    async def generate_structured(self, request: LLMRequest, schema: dict[str, Any]) -> LLMResponse:
        raise LLMCapabilityError()

    async def list_models(self) -> list[ProviderModelInfo]:
        """Models the configured credentials can use. Used only by scripts/list_llm_models.py."""
        raise LLMCapabilityError()

    async def aclose(self) -> None:
        return None
