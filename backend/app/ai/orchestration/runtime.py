"""Per-process AI runtime: settings, model registry and a lazy provider handle.

Routes get it through the `get_ai_runtime` dependency so tests can swap in the fake provider without
touching environment variables. Nothing here imports a vendor SDK.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.errors import LLMNotConfiguredError
from app.ai.model_registry import ModelRegistry, build_registry
from app.ai.providers.base import LLMProvider
from app.ai.providers.registry import get_provider
from app.core.config import Settings, get_settings
from app.database.connection import AsyncSessionLocal


@dataclass(frozen=True)
class AiRuntime:
    settings: Settings
    registry: ModelRegistry
    provider_factory: Callable[[], LLMProvider]

    def provider(self) -> LLMProvider:
        return self.provider_factory()


@lru_cache
def _default_runtime() -> AiRuntime:
    settings = get_settings()
    registry = build_registry(settings)

    def factory() -> LLMProvider:
        if not registry.configured or registry.provider is None:
            raise LLMNotConfiguredError()
        return get_provider(registry.provider, settings)

    return AiRuntime(settings=settings, registry=registry, provider_factory=factory)


def get_ai_runtime() -> AiRuntime:
    return _default_runtime()


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Sessions for work that outlives the request (streaming tasks). Tests override this."""
    return AsyncSessionLocal


Runtime = Annotated[AiRuntime, Depends(get_ai_runtime)]
SessionFactory = Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)]
