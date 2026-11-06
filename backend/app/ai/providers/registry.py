"""Maps a provider name to its adapter. The ONLY place that does so
(AI_ARCHITECTURE.md section 6.1).

Adapters are loaded lazily by dotted path so importing this module never imports a vendor SDK, and
an app with no provider configured never loads one. To add a provider: one adapter file plus one
line in `_ADAPTERS` below.
"""

from __future__ import annotations

import importlib

from app.ai.errors import LLMNotConfiguredError
from app.ai.providers.base import LLMProvider
from app.core.config import Settings

_ADAPTERS: dict[str, str] = {
    "gemini": "app.ai.providers.gemini_provider:GeminiProvider",
    "fake": "app.ai.providers.fake_provider:FakeProvider",
}

_instances: dict[str, LLMProvider] = {}


def known_providers() -> list[str]:
    return sorted(_ADAPTERS)


def provider_class(name: str) -> type[LLMProvider]:
    path = _ADAPTERS.get(name.lower())
    if path is None:
        raise LLMNotConfiguredError()
    module_name, _, class_name = path.partition(":")
    cls = getattr(importlib.import_module(module_name), class_name)
    if not (isinstance(cls, type) and issubclass(cls, LLMProvider)):
        raise LLMNotConfiguredError()
    return cls


def get_provider(name: str, settings: Settings) -> LLMProvider:
    """Build (once) and return the adapter for `name`."""
    key = name.lower()
    if key not in _instances:
        _instances[key] = provider_class(key).create(settings)
    return _instances[key]


async def close_providers() -> None:
    for provider in list(_instances.values()):
        await provider.aclose()
    _instances.clear()


def reset_providers() -> None:
    """Forget cached adapters (tests)."""
    _instances.clear()
