"""Model registry (D-37, AI_ARCHITECTURE.md section 6.2). No vendor SDK imports.

Built from settings. `LLM_DEFAULT_MODEL` becomes internal id "default"; each entry of
`LLM_ALLOWED_MODELS` becomes an extra model. Provider model ids are never literals in code (D-38).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from app.ai.errors import LLMInvalidModelError, LLMNotConfiguredError
from app.ai.providers.registry import provider_class
from app.ai.types import Capabilities
from app.core.config import Settings

DEFAULT_MODEL_ID = "default"
FAKE_DEFAULT_MODEL = "fake-model"
CONFIG_VERSION = "1"


@dataclass(frozen=True, slots=True)
class ModelConfig:
    internal_id: str
    provider: str
    provider_model_id: str
    display_name: str
    enabled: bool
    capabilities: Capabilities
    max_input_tokens: int | None = None  # verified limit; None = unknown
    max_output_tokens: int | None = None
    default_temperature: float | None = None
    config_version: str = CONFIG_VERSION

    def public_dict(self, *, is_default: bool) -> dict[str, object]:
        """Safe metadata for the frontend. Never keys, endpoints or provider internals."""
        return {
            "id": self.internal_id,
            "display_name": self.display_name,
            "is_default": is_default,
            "capabilities": self.capabilities.to_dict(),
            "max_input_tokens": self.max_input_tokens,
            "max_output_tokens": self.max_output_tokens,
        }


def _slug(provider_model_id: str) -> str:
    return "m-" + re.sub(r"[^a-z0-9]+", "-", provider_model_id.lower()).strip("-")


class ModelRegistry:
    def __init__(self, provider: str | None, models: list[ModelConfig]) -> None:
        self.provider = provider
        self._models = {m.internal_id: m for m in models}

    @property
    def configured(self) -> bool:
        return bool(self._models)

    def enabled(self) -> list[ModelConfig]:
        return [m for m in self._models.values() if m.enabled]

    @property
    def default(self) -> ModelConfig:
        model = self._models.get(DEFAULT_MODEL_ID)
        if model is None or not model.enabled:
            raise LLMNotConfiguredError()
        return model

    def resolve(self, internal_id: str | None) -> ModelConfig:
        """The default for None; LLM_INVALID_MODEL for an unknown or disabled id."""
        if not self.configured:
            raise LLMNotConfiguredError()
        if internal_id is None or internal_id == "":
            return self.default
        model = self._models.get(internal_id)
        if model is None or not model.enabled:
            raise LLMInvalidModelError()
        return model


def build_registry(settings: Settings) -> ModelRegistry:
    """An empty registry means "not configured": the app still runs (D-58)."""
    provider = settings.llm_provider.lower()
    if not provider:
        return ModelRegistry(None, [])

    cls = provider_class(provider)
    default_id = settings.llm_default_model or (FAKE_DEFAULT_MODEL if provider == "fake" else "")
    if not default_id:
        return ModelRegistry(provider, [])

    base = ModelConfig(
        internal_id=DEFAULT_MODEL_ID,
        provider=provider,
        provider_model_id=default_id,
        display_name=default_id,
        enabled=True,
        capabilities=cls.capabilities,
        max_input_tokens=settings.llm_model_max_input_tokens,
        max_output_tokens=settings.llm_model_max_output_tokens,
    )
    models = [base]
    for extra in (m.strip() for m in settings.llm_allowed_models.split(",")):
        if extra and extra != default_id:
            models.append(
                replace(
                    base,
                    internal_id=_slug(extra),
                    provider_model_id=extra,
                    display_name=extra,
                    max_input_tokens=None,
                    max_output_tokens=None,
                )
            )
    return ModelRegistry(provider, models)
