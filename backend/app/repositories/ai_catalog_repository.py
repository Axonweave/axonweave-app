"""Persistence for the provider/model/prompt catalogue (written at startup, read-mostly after)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.llm_provider import LLMModel, LLMModelPrice, LLMProvider
from app.models.prompt_template import PromptTemplate


class AiCatalogRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # providers / models ──────────────────────────────────────────────────────

    async def upsert_provider(self, name: str, display_name: str) -> LLMProvider:
        row = (
            await self.db.execute(select(LLMProvider).where(LLMProvider.provider_name == name))
        ).scalar_one_or_none()
        if row is None:
            row = LLMProvider(provider_name=name, display_name=display_name, is_enabled=True)
            self.db.add(row)
        else:
            row.display_name = display_name
            row.is_enabled = True
        await self.db.flush()
        return row

    async def clear_default_model(self) -> None:
        await self.db.execute(
            update(LLMModel).where(LLMModel.is_default.is_(True)).values(is_default=False)
        )

    async def upsert_model(
        self, provider_id: Any, internal_id: str, fields: dict[str, Any]
    ) -> LLMModel:
        row = (
            await self.db.execute(select(LLMModel).where(LLMModel.internal_id == internal_id))
        ).scalar_one_or_none()
        if row is None:
            row = LLMModel(provider_id=provider_id, internal_id=internal_id, **fields)
            self.db.add(row)
        else:
            for k, v in fields.items():
                setattr(row, k, v)
        await self.db.flush()
        return row

    async def disable_models_except(self, internal_ids: Sequence[str]) -> None:
        await self.db.execute(
            update(LLMModel)
            .where(LLMModel.internal_id.not_in(list(internal_ids)))
            .values(is_enabled=False, is_default=False)
        )

    async def ensure_price(
        self, model_id: Any, pricing_version: str, fields: dict[str, Any]
    ) -> None:
        exists = (
            await self.db.execute(
                select(LLMModelPrice.id).where(
                    LLMModelPrice.model_id == model_id,
                    LLMModelPrice.pricing_version == pricing_version,
                )
            )
        ).first()
        if exists is None:
            self.db.add(LLMModelPrice(model_id=model_id, pricing_version=pricing_version, **fields))
            await self.db.flush()

    async def get_model(self, internal_id: str) -> LLMModel | None:
        return (
            await self.db.execute(select(LLMModel).where(LLMModel.internal_id == internal_id))
        ).scalar_one_or_none()

    # prompts ─────────────────────────────────────────────────────────────────

    async def get_prompt(self, prompt_key: str, version: int) -> PromptTemplate | None:
        return (
            await self.db.execute(
                select(PromptTemplate).where(
                    PromptTemplate.prompt_key == prompt_key, PromptTemplate.version == version
                )
            )
        ).scalar_one_or_none()

    async def add_prompt(
        self, prompt_key: str, version: int, content: str, sha256: str
    ) -> PromptTemplate:
        row = PromptTemplate(
            prompt_key=prompt_key,
            version=version,
            content=content,
            content_sha256=sha256,
            is_active=False,
        )
        self.db.add(row)
        await self.db.flush()
        return row

    async def set_active_prompt(self, prompt_key: str, version: int) -> None:
        # Deactivate first so the partial unique index (one active per key) is never violated.
        await self.db.execute(
            update(PromptTemplate)
            .where(PromptTemplate.prompt_key == prompt_key, PromptTemplate.version != version)
            .values(is_active=False)
        )
        await self.db.execute(
            update(PromptTemplate)
            .where(PromptTemplate.prompt_key == prompt_key, PromptTemplate.version == version)
            .values(is_active=True)
        )
