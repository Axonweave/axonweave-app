"""Maps an embedding provider name to its adapter (the only place that does). Adapters load
lazily by dotted path, so importing this never imports a vendor SDK."""

from __future__ import annotations

import importlib

from app.core.config import Settings
from app.embeddings.base import EmbeddingProvider
from app.embeddings.errors import EmbeddingNotConfiguredError

_ADAPTERS: dict[str, str] = {
    "gemini": "app.embeddings.gemini_provider:GeminiEmbeddingProvider",
    "fake": "app.embeddings.fake_provider:FakeEmbeddingProvider",
}
_instances: dict[str, EmbeddingProvider] = {}


def known_providers() -> list[str]:
    return sorted(_ADAPTERS)


def embedding_configured(settings: Settings) -> bool:
    return bool(settings.embedding_provider) and bool(
        settings.embedding_model or settings.embedding_provider.lower() == "fake"
    )


def get_embedding_provider(settings: Settings) -> EmbeddingProvider:
    name = settings.embedding_provider.lower()
    path = _ADAPTERS.get(name)
    if path is None:
        raise EmbeddingNotConfiguredError()
    if name not in _instances:
        module_name, _, class_name = path.partition(":")
        cls = getattr(importlib.import_module(module_name), class_name)
        _instances[name] = cls.create(settings)
    return _instances[name]


async def close_embedding_providers() -> None:
    for provider in list(_instances.values()):
        await provider.aclose()
    _instances.clear()


def reset_embedding_providers() -> None:
    _instances.clear()
