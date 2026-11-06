"""Conversation, message and model services (route -> service -> repository)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.errors import (
    ConversationNotFoundError,
    LLMNotConfiguredError,
    MessageNotFoundError,
)
from app.ai.orchestration.runtime import AiRuntime
from app.ai.providers.registry import provider_class
from app.models.conversation import Conversation
from app.models.message import Message, MessageFeedback
from app.models.user import User
from app.repositories.ai_conversation_repository import AiConversationRepository
from app.repositories.ai_message_repository import AiMessageRepository


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

    def capabilities(self) -> dict[str, Any]:
        return self._runtime.registry.default.capabilities.to_dict()
