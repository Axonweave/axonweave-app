"""Startup sync of the model registry and prompt catalogue into the database (D-37, D-41).

Idempotent. A released prompt version is immutable: if the code's content for an existing
(key, version) differs from the stored hash, startup fails loudly instead of rewriting history.
"""

from __future__ import annotations

from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.model_registry import ModelRegistry, _slug
from app.ai.prompts.registry import PROMPTS, active_prompt
from app.ai.providers.registry import provider_class
from app.ai.usage.pricing import find_price
from app.core.logging import get_logger
from app.repositories.ai_catalog_repository import AiCatalogRepository

logger = get_logger(__name__)


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
                    "input_price_per_1m": price.input_per_million,
                    "output_price_per_1m": price.output_per_million,
                    "source_note": price.source_url,
                },
            )
    await repo.disable_models_except(keys)


async def sync_catalog_at_startup(
    session_factory: async_sessionmaker[AsyncSession], registry: ModelRegistry
) -> bool:
    """Sync prompts and models without ever blocking startup on an unmigrated database.

    On a fresh stack the app can start before `alembic upgrade head` has run. The tables are then
    missing, which must not stop the rest of the app (D-58), so this logs and returns False. A
    released prompt whose text changed (PromptImmutableError) is a real error and still propagates.
    """
    try:
        async with session_factory() as session:
            await sync_prompts(session)
            await sync_models(session, registry)
            await session.commit()
    except DBAPIError:
        logger.warning("ai_catalog_sync_skipped", reason="database_not_ready")
        return False
    return True
