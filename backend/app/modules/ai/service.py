"""Conversation, message and model services (route -> service -> repository)."""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.errors import (
    ConversationNotFoundError,
    LLMNotConfiguredError,
    MessageNotFoundError,
)
from app.ai.orchestration.runtime import AiRuntime
from app.ai.orchestration.streaming import (
    CANCEL_WAIT_SECONDS,
    GenerationRegistry,
    get_generation_registry,
)
from app.ai.providers.registry import provider_class
from app.models.conversation import Conversation
from app.models.message import Message, MessageFeedback
from app.models.user import User
from app.repositories.ai_conversation_repository import AiConversationRepository
from app.repositories.ai_message_repository import AiMessageRepository
from app.repositories.ai_usage_repository import AiUsageRepository, UsageAggregate


class ConversationService:
    def __init__(self, db: AsyncSession, runtime: AiRuntime) -> None:
        self._repo = AiConversationRepository(db)
        self._runtime = runtime

    async def create(self, *, user: User, title: str | None, model_id: str | None) -> Conversation:
        resolved: str | None = None
        if model_id is not None:
            # Validates the id (invalid or disabled -> LLM_INVALID_MODEL, none configured -> 503).
            resolved = self._runtime.registry.resolve(model_id).internal_id
        return await self._repo.create(user_id=user.id, title=title, model_id=resolved)

    async def list(
        self, *, user: User, status: str | None, q: str | None, limit: int, offset: int
    ) -> tuple[list[Conversation], int]:
        return await self._repo.list_owned(
            user_id=user.id, status=status, q=q, limit=limit, offset=offset
        )

    async def get(self, *, user: User, conversation_id: uuid.UUID) -> Conversation:
        conv = await self._repo.get_owned(conversation_id=conversation_id, user_id=user.id)
        if conv is None:
            raise ConversationNotFoundError()
        return conv

    async def rename(self, *, user: User, conversation_id: uuid.UUID, title: str) -> Conversation:
        conv = await self.get(user=user, conversation_id=conversation_id)
        conv.title = title
        return conv

    async def archive(self, *, user: User, conversation_id: uuid.UUID) -> Conversation:
        conv = await self.get(user=user, conversation_id=conversation_id)
        conv.status = "archived"
        return conv

    async def delete(self, *, user: User, conversation_id: uuid.UUID) -> None:
        """Hard delete. Messages and feedback cascade; usage rows stay with NULL links (D-53)."""
        deleted = await self._repo.delete_owned(conversation_id=conversation_id, user_id=user.id)
        if not deleted:
            raise ConversationNotFoundError()


class MessageService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._conversations = AiConversationRepository(db)
        self._messages = AiMessageRepository(db)

    async def list(
        self, *, user: User, conversation_id: uuid.UUID, limit: int, offset: int
    ) -> tuple[list[Message], int]:
        conv = await self._conversations.get_owned(conversation_id=conversation_id, user_id=user.id)
        if conv is None:
            raise ConversationNotFoundError()
        return await self._messages.list_for_conversation(
            conversation_id=conversation_id, user_id=user.id, limit=limit, offset=offset
        )

    async def cancel(
        self,
        *,
        user: User,
        conversation_id: uuid.UUID,
        message_id: uuid.UUID,
        registry: GenerationRegistry | None = None,
    ) -> Message:
        """Stop a running generation (D-45). Ownership is checked first; anything that is not
        the caller's answer in this conversation is a 404. If nothing is running (already
        finished, or owned by another process) the message's current state is returned."""
        conv = await self._conversations.get_owned(conversation_id=conversation_id, user_id=user.id)
        message = await self._messages.get_owned(message_id=message_id, user_id=user.id)
        if (
            conv is None
            or message is None
            or message.conversation_id != conv.id
            or message.role != "assistant"
        ):
            raise MessageNotFoundError()
        handle = (registry or get_generation_registry()).get(message.id, user.id)
        if handle is not None:
            handle.request_cancel("user")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(handle.done.wait(), CANCEL_WAIT_SECONDS)
            await self._db.refresh(message)
        return message

    async def submit_feedback(
        self, *, user: User, message_id: uuid.UUID, rating: str, text: str | None
    ) -> MessageFeedback:
        message = await self._messages.get_owned(message_id=message_id, user_id=user.id)
        # Feedback only makes sense on a finished answer; anything else looks like "not found".
        if message is None or message.role != "assistant" or message.status != "completed":
            raise MessageNotFoundError()
        return await self._messages.upsert_feedback(
            message_id=message.id, user_id=user.id, rating=rating, text=text
        )


class ModelService:
    """Safe, read-only model metadata. Nothing from the provider or the environment leaks."""

    def __init__(self, runtime: AiRuntime) -> None:
        self._runtime = runtime

    def _out(self, model: Any, *, is_default: bool) -> dict[str, Any]:
        data = model.public_dict(is_default=is_default)
        provider = self._runtime.registry.provider
        data["is_test_provider"] = provider is not None and provider_class(provider).kind == "test"
        return data

    def list(self) -> list[dict[str, Any]]:
        registry = self._runtime.registry
        if not registry.configured:
            raise LLMNotConfiguredError()
        default_id = registry.default.internal_id
        return [self._out(m, is_default=m.internal_id == default_id) for m in registry.enabled()]

    def default(self) -> dict[str, Any]:
        return self._out(self._runtime.registry.default, is_default=True)

    def status(self) -> dict[str, Any]:
        registry = self._runtime.registry
        provider = registry.provider if registry.configured else None
        cls = provider_class(provider) if provider else None
        return {
            "configured": registry.configured,
            "provider_display_name": cls.display_name if cls else None,
            "is_test_provider": cls is not None and cls.kind == "test",
            "max_input_chars": self._runtime.settings.llm_max_input_chars,
        }

    def capabilities(self) -> dict[str, Any]:
        return self._runtime.registry.default.capabilities.to_dict()


def _fold(rows: list[UsageAggregate]) -> dict[str, Any]:
    """Combine grouped rows into totals. Costs stay per currency and unknown stays unknown."""
    costs: dict[str, Decimal] = {}
    totals = {
        "requests": 0,
        "failed_requests": 0,
        "cancelled_requests": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "token_known_requests": 0,
        "cost_known_requests": 0,
    }
    for r in rows:
        totals["requests"] += r.requests
        totals["failed_requests"] += r.failed
        totals["cancelled_requests"] += r.cancelled
        totals["input_tokens"] += r.input_tokens
        totals["output_tokens"] += r.output_tokens
        totals["token_known_requests"] += r.token_known_requests
        totals["cost_known_requests"] += r.cost_known_requests
        if r.currency and r.cost_known_requests:
            costs[r.currency] = costs.get(r.currency, Decimal(0)) + r.cost
    return {
        **totals,
        "total_tokens": totals["input_tokens"] + totals["output_tokens"],
        "cost_by_currency": [{"currency": c, "amount": a} for c, a in sorted(costs.items())],
    }


class UsageService:
    """The caller's own usage only: every query is filtered by user_id (spec 14.4)."""

    def __init__(self, db: AsyncSession) -> None:
        self._repo = AiUsageRepository(db)

    @staticmethod
    def _since(days: int) -> datetime:
        return datetime.now(UTC) - timedelta(days=days)

    async def list(
        self, *, user: User, status: str | None, days: int, limit: int, offset: int
    ) -> tuple[list[dict[str, Any]], int]:
        rows, total = await self._repo.list_for_user(
            user_id=user.id, status=status, since=self._since(days), limit=limit, offset=offset
        )
        out = []
        for record, model_internal_id, display_name in rows:
            known = [t for t in (record.input_tokens, record.output_tokens) if t is not None]
            out.append(
                {
                    "id": record.id,
                    "created_at": record.created_at,
                    "conversation_id": record.conversation_id,
                    "message_id": record.message_id,
                    "model_id": model_internal_id,
                    "model_display_name": display_name,
                    "request_status": record.request_status,
                    "error_code": record.error_code,
                    "input_tokens": record.input_tokens,
                    "output_tokens": record.output_tokens,
                    "reasoning_tokens": record.reasoning_tokens,
                    "total_tokens": sum(known) if known else None,
                    "usage_source": record.usage_source,
                    "estimated_cost": record.estimated_cost,
                    "currency": record.currency,
                    "pricing_version": record.pricing_version,
                    "duration_ms": record.duration_ms,
                }
            )
        return out, total

    async def summary(self, *, user: User, days: int) -> dict[str, Any]:
        since = self._since(days)
        rows = await self._repo.aggregate(user_id=user.id, since=since)
        return {**_fold(rows), "days": days, "since": since}

    async def by_model(self, *, user: User, days: int) -> list[dict[str, Any]]:
        rows = await self._repo.aggregate(user_id=user.id, since=self._since(days))
        grouped: dict[str, list[UsageAggregate]] = {}
        for r in rows:
            grouped.setdefault(r.model_internal_id, []).append(r)
        return [
            {"model_id": mid, "display_name": group[0].model_display_name, **_fold(group)}
            for mid, group in grouped.items()
        ]
