"""Startup sync of the model registry and prompt catalogue into the database (D-37, D-41).

Idempotent. A released prompt version is immutable: if the code's content for an existing
(key, version) differs from the stored hash, startup fails loudly instead of rewriting history.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.model_registry import ModelRegistry, _slug
from app.ai.prompts.registry import PROMPTS, active_prompt
from app.ai.providers.registry import provider_class
from app.ai.usage.pricing import find_price
from app.repositories.ai_catalog_repository import AiCatalogRepository


class PromptImmutableError(RuntimeError):
    pass


async def sync_prompts(db: AsyncSession) -> None:
    repo = AiCatalogRepository(db)
    for prompt in PROMPTS:
        existing = await repo.get_prompt(prompt.prompt_key, prompt.version)
        if existing is None:
            await repo.add_prompt(prompt.prompt_key, prompt.version, prompt.content, prompt.sha256)
        elif existing.content_sha256 != prompt.sha256:
            raise PromptImmutableError(
                f"Prompt {prompt.prompt_key} v{prompt.version} changed; add a new version instead."
            )
    for key in {p.prompt_key for p in PROMPTS}:
        await repo.set_active_prompt(key, active_prompt(key).version)


async def sync_models(db: AsyncSession, registry: ModelRegistry) -> None:
    """No-op when no provider is configured; the app still runs (D-58)."""
    if not registry.configured or registry.provider is None:
        return
    repo = AiCatalogRepository(db)
    cls = provider_class(registry.provider)
    provider = await repo.upsert_provider(registry.provider, cls.display_name)

    await repo.clear_default_model()
    keys: list[str] = []
    default_id = registry.default.provider_model_id
    for cfg in registry.enabled():
        key = _slug(cfg.provider_model_id)
        keys.append(key)
        model = await repo.upsert_model(
            provider.id,
            key,
            {
                "provider_model_id": cfg.provider_model_id,
                "display_name": cfg.display_name,
                "is_enabled": True,
                "is_default": cfg.provider_model_id == default_id,
                "max_input_tokens": cfg.max_input_tokens,
                "max_output_tokens": cfg.max_output_tokens,
                "capabilities": cfg.capabilities.to_dict(),
            },
        )
        price = find_price(cfg.provider, cfg.provider_model_id)
        if price is not None:
            await repo.ensure_price(
                model.id,
                price.pricing_version,
                {
                    "currency": price.currency,
                    "input_per_million": price.input_per_million,
                    "output_per_million": price.output_per_million,
                    "source_url": price.source_url,
                },
            )
    await repo.disable_models_except(keys)
