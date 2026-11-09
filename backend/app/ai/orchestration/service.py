"""AI orchestration: validate -> save user message -> build context -> call provider -> save answer.

The steps are separate methods so streaming, regenerate and cancel (M3) reuse them:

    prepare()          validation, quotas, and the short locked transaction that writes the user
                       message and a `pending` assistant message (AI_ARCHITECTURE.md 7.1, steps 1-4)
    run_generation()   context + provider call with retries (non-streaming)
    finalize_*()       the transaction that stores the outcome and the usage row

Rules enforced here, in code and never by prompts:
- the conversation is loaded by (id, user_id); anything else is a 404;
- a failed generation is stored as `failed` with an error code and is never returned as a success;
- the provider call runs with no row locks held;
- message text is never logged (D-51).
"""

from __future__ import annotations

import asyncio
import contextlib
import random
import re
import time
import uuid
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from app.ai.errors import (
    AiError,
    AiQuotaExceededError,
    AiTooManyActiveError,
    ConversationArchivedError,
    ConversationNotFoundError,
    GenerationInProgressError,
    InputTooLongError,
    LLMBadResponseError,
    LLMError,
    LLMInvalidModelError,
    LLMNotConfiguredError,
    MessageNotFoundError,
    RegenerateNotAllowedError,
)
from app.ai.model_registry import ModelConfig
from app.ai.orchestration.context import (
    ContextManager,
    ContextRequest,
    ContextResult,
    ConversationHistory,
)
from app.ai.orchestration.runtime import AiRuntime
from app.ai.prompts.rag import DOCUMENT_FIRST_KEY, DOCUMENT_ONLY_KEY
from app.ai.prompts.registry import PromptDefinition, active_prompt
from app.ai.rag import (
    INSUFFICIENT_REPLY,
    build_query,
    build_user_turn,
    validate_citations,
)
from app.ai.sync import sync_models
from app.ai.types import (
    LLMMessage,
    LLMRequest,
    LLMResponse,
    StreamDelta,
    StreamEvent,
    TimeoutPolicy,
    Usage,
    UsageSource,
)
from app.ai.usage.pricing import estimate_cost, find_price
from app.core.logging import get_logger
from app.core.rate_limit import RateLimiter, get_rate_limiter
from app.models.conversation import Conversation
from app.models.llm_provider import LLMModel
from app.models.message import Message
from app.models.message_citation import MessageCitation
from app.models.user import User
from app.repositories.ai_catalog_repository import AiCatalogRepository
from app.repositories.ai_conversation_repository import AiConversationRepository
from app.repositories.ai_message_repository import AiMessageRepository
from app.repositories.ai_usage_repository import AiUsageRepository
from app.repositories.message_citation_repository import MessageCitationRepository
from app.repositories.retrieval_repository import ChunkHit
from app.retrieval.embedder import make_query_embedder
from app.retrieval.scope import ResolvedScope, ScopeResolver
from app.retrieval.searcher import Searcher

logger = get_logger(__name__)

PROMPT_KEY = "academic_tutor"
TITLE_MAX_CHARS = 60
RETRY_BASE_DELAY = 0.5  # seconds; doubled per attempt, capped at RETRY_MAX_DELAY
RETRY_MAX_DELAY = 4.0
ACTIVE_CAP_RETRY_AFTER = 5  # seconds; a generation usually finishes sooner
_WHITESPACE = re.compile(r"\s+")


def derive_title(content: str) -> str:
    """Deterministic title from the first message: no LLM call (D-55)."""
    collapsed = _WHITESPACE.sub(" ", content).strip()
    if len(collapsed) <= TITLE_MAX_CHARS:
        return collapsed
    return collapsed[: TITLE_MAX_CHARS - 1].rstrip() + "…"


@dataclass
class Prepared:
    """Everything the generation step needs, captured while the locks were held."""

    conversation: Conversation
    user_message: Message
    assistant_message: Message
    model: ModelConfig
    catalog_model: LLMModel
    system_prompt: str
    prompt_version: int
    answer_mode: str = "general"


@dataclass
class GenerationResult:
    conversation: Conversation
    user_message: Message
    assistant_message: Message
    usage: Usage
    citations: list[MessageCitation] = field(default_factory=list)


class AiService:
    def __init__(
        self,
        db: AsyncSession,
        runtime: AiRuntime,
        limiter: RateLimiter | None = None,
    ) -> None:
        self._db = db
        self._runtime = runtime
        self._settings = runtime.settings
        self._limiter = limiter or get_rate_limiter()
        self._conversations = AiConversationRepository(db)
        self._messages = AiMessageRepository(db)
        self._usage = AiUsageRepository(db)
        self._catalog = AiCatalogRepository(db)

    # ── non-streaming entry points ───────────────────────────────────────────

    async def send_message(
        self,
        *,
        user: User,
        conversation_id: uuid.UUID,
        content: str,
        model_id: str | None,
        answer_mode: str | None = None,
    ) -> GenerationResult:
        prepared = await self.prepare(
            user=user,
            conversation_id=conversation_id,
            content=content,
            model_id=model_id,
            answer_mode=answer_mode,
        )
        return await self.run_generation(user=user, prepared=prepared)

    async def regenerate(
        self,
        *,
        user: User,
        conversation_id: uuid.UUID,
        message_id: uuid.UUID,
        model_id: str | None,
    ) -> GenerationResult:
        prepared = await self.prepare_regenerate(
            user=user, conversation_id=conversation_id, message_id=message_id, model_id=model_id
        )
        return await self.run_generation(user=user, prepared=prepared)

    # ── step 1: validate, authorise, reserve ─────────────────────────────────

    async def _owned_active_conversation(
        self, user: User, conversation_id: uuid.UUID
    ) -> Conversation:
        # Ownership first: a conversation that is not yours does not exist (rule 2).
        conversation = await self._conversations.get_owned(
            conversation_id=conversation_id, user_id=user.id
        )
        if conversation is None:
            raise ConversationNotFoundError()
        if conversation.status == "archived":
            raise ConversationArchivedError()
        return conversation

    async def _lock_for_generation(
        self, user_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> Conversation:
        """Transaction A locks, always user first and conversation second (D-42, D-43)."""
        await self._conversations.lock_user(user_id)
        if await self._conversations.count_active_generations(user_id) >= (
            self._settings.ai_max_active_generations_per_user
        ):
            await self._db.rollback()
            raise AiTooManyActiveError(retry_after=ACTIVE_CAP_RETRY_AFTER)
        locked = await self._conversations.get_owned(
            conversation_id=conversation_id, user_id=user_id, for_update=True
        )
        if locked is None:  # deleted while we waited for the lock
            await self._db.rollback()
            raise ConversationNotFoundError()
        if await self._messages.has_active_generation(conversation_id=locked.id, user_id=user_id):
            await self._db.rollback()
            raise GenerationInProgressError()
        return locked

    async def prepare(
        self,
        *,
        user: User,
        conversation_id: uuid.UUID,
        content: str,
        model_id: str | None,
        answer_mode: str | None = None,
    ) -> Prepared:
        conversation = await self._owned_active_conversation(user, conversation_id)
        if model_id:
            model = self._runtime.registry.resolve(model_id)  # an explicit choice must be valid
        else:
            try:
                model = self._runtime.registry.resolve(conversation.model_id)
            except LLMInvalidModelError:
                # The model this conversation was started with is no longer enabled (provider or
                # configuration changed): continue on the default instead of locking the chat.
                model = self._runtime.registry.resolve(None)
        if len(content) > self._settings.llm_max_input_chars:
            raise InputTooLongError()

        await self._enforce_limits(user.id)
        catalog_model = await self._catalog_model(model)
        mode = _effective_mode(conversation, answer_mode)
        prompt = active_prompt(_prompt_key(mode))

        locked = await self._lock_for_generation(user.id, conversation_id)
        try:
            sequence = await self._messages.next_sequence(
                conversation_id=locked.id, user_id=user.id
            )
            user_message = await self._messages.add(
                conversation_id=locked.id,
                user_id=user.id,
                role="user",
                status="completed",
                sequence_number=sequence,
                content=content,
                completed_at=datetime.now(UTC),
            )
            assistant_message = await self._add_pending_assistant(
                locked, user, sequence + 1, model, prompt, regenerates=None, answer_mode=mode
            )
        except IntegrityError:
            # The partial unique index: another generation is already active here (D-43).
            await self._db.rollback()
            raise GenerationInProgressError() from None
        if not locked.title:
            locked.title = derive_title(content)
        locked.model_id = model.internal_id
        locked.last_message_at = datetime.now(UTC)
        await self._db.commit()
        return Prepared(
            conversation=locked,
            user_message=user_message,
            assistant_message=assistant_message,
            model=model,
            catalog_model=catalog_model,
            system_prompt=prompt.content,
            prompt_version=prompt.version,
            answer_mode=mode,
        )

    async def _add_pending_assistant(
        self,
        conversation: Conversation,
        user: User,
        sequence: int,
        model: ModelConfig,
        prompt: PromptDefinition,
        *,
        regenerates: uuid.UUID | None,
        answer_mode: str = "general",
    ) -> Message:
        scoped = answer_mode != "general"
        return await self._messages.add(
            conversation_id=conversation.id,
            user_id=user.id,
            role="assistant",
            status="pending",
            sequence_number=sequence,
            content="",
            model_id=model.internal_id,
            prompt_key=prompt.prompt_key,
            prompt_version=prompt.version,
            regenerates_message_id=regenerates,
            scope_type=conversation.scope_type if scoped else None,
            scope_id=conversation.scope_id if scoped else None,
            answer_mode=answer_mode if scoped else None,
        )

    def _model_for_regenerate(self, requested: str | None, target: Message) -> ModelConfig:
        registry = self._runtime.registry
        if requested:
            return registry.resolve(requested)
        try:
            return registry.resolve(target.model_id)
        except LLMInvalidModelError:  # the old model was disabled: fall back to the default
            return registry.resolve(None)

    async def prepare_regenerate(
        self,
        *,
        user: User,
        conversation_id: uuid.UUID,
        message_id: uuid.UUID,
        model_id: str | None,
    ) -> Prepared:
        """A new attempt at the latest answer (D-42). The old one is kept, marked superseded."""
        conversation = await self._owned_active_conversation(user, conversation_id)
        target = await self._messages.get_owned(message_id=message_id, user_id=user.id)
        if (
            target is None
            or target.conversation_id != conversation.id
            or target.role != "assistant"
        ):
            raise MessageNotFoundError()
        model = self._model_for_regenerate(model_id, target)

        await self._enforce_limits(user.id)
        catalog_model = await self._catalog_model(model)
        mode = _effective_mode(conversation, target.answer_mode)
        prompt = active_prompt(_prompt_key(mode))

        locked = await self._lock_for_generation(user.id, conversation_id)
        await self._db.refresh(target)  # re-read under the lock: a concurrent click may have won
        latest = await self._messages.latest_active_assistant(
            conversation_id=locked.id, user_id=user.id
        )
        if latest is None or latest.id != target.id or target.superseded_at is not None:
            await self._db.rollback()
            raise RegenerateNotAllowedError()
        user_message = await self._messages.previous_user_message(
            conversation_id=locked.id, user_id=user.id, before_sequence=target.sequence_number
        )
        if user_message is None:
            await self._db.rollback()
            raise RegenerateNotAllowedError()
        try:
            sequence = await self._messages.next_sequence(
                conversation_id=locked.id, user_id=user.id
            )
            target.superseded_at = datetime.now(UTC)
            assistant_message = await self._add_pending_assistant(
                locked, user, sequence, model, prompt, regenerates=target.id, answer_mode=mode
            )
        except IntegrityError:
            await self._db.rollback()
            raise GenerationInProgressError() from None
        locked.model_id = model.internal_id
        locked.last_message_at = datetime.now(UTC)
        await self._db.commit()
        return Prepared(
            conversation=locked,
            user_message=user_message,
            assistant_message=assistant_message,
            model=model,
            catalog_model=catalog_model,
            system_prompt=prompt.content,
            prompt_version=prompt.version,
            answer_mode=mode,
        )

    async def _enforce_limits(self, user_id: uuid.UUID) -> None:
        s = self._settings
        try:
            await self._limiter.check(f"ai:user:{user_id}", s.ai_requests_per_minute_per_user, 60)
        except HTTPException:
            raise AiQuotaExceededError(retry_after=60) from None
        reset_in = _seconds_until_utc_midnight()
        if await self._usage.requests_today(user_id) >= s.ai_daily_message_quota:
            raise AiQuotaExceededError(retry_after=reset_in)
        if await self._usage.tokens_today(user_id) >= s.ai_daily_token_quota:
            raise AiQuotaExceededError(retry_after=reset_in)

    async def _catalog_model(self, model: ModelConfig) -> LLMModel:
        """The catalogue row for usage records. Created on first use if startup could not (D-58)."""
        row = await self._catalog.get_model(model.internal_id)
        if row is None:
            try:
                await sync_models(self._db, self._runtime.registry)
                await self._db.commit()
            except IntegrityError:  # another request synced at the same moment
                await self._db.rollback()
            row = await self._catalog.get_model(model.internal_id)
        if row is None:
            raise LLMNotConfiguredError()
        return row

    # ── step 2: context + provider ───────────────────────────────────────────

    async def build_context(self, *, user: User, prepared: Prepared) -> ContextResult:
        sources: tuple[ChunkHit, ...] = ()
        new_message = prepared.user_message.content
        if prepared.answer_mode != "general":
            sources = await self._retrieve(user, prepared)
            if not sources and prepared.answer_mode == "document_only":
                return ContextResult(
                    system_prompt=prepared.system_prompt,
                    messages=[],
                    estimated=True,
                    dropped_messages=0,
                    input_tokens=0,
                    canned_reply=INSUFFICIENT_REPLY,
                )
            if sources:
                new_message = build_user_turn(new_message, sources)
        provider = self._runtime.provider()
        model = prepared.model
        settings = self._settings
        budget = (model.max_input_tokens or settings.llm_fallback_input_tokens) - (
            settings.llm_max_output_tokens
        )

        async def counter(system: str, messages: list[LLMMessage]) -> int | None:
            if not model.capabilities.count_tokens:
                return None
            probe = self.make_request(prepared, system, messages)
            return await provider.count_tokens(probe)

        manager = ContextManager(
            [ConversationHistory(self._messages, limit=settings.llm_history_limit)],
            budget_tokens=max(budget, 1),
            counter=counter,
        )
        result = await manager.build(
            ContextRequest(
                conversation_id=prepared.conversation.id,
                user_id=user.id,
                new_message=new_message,
                before_sequence=prepared.user_message.sequence_number,
            ),
            system_prompt=prepared.system_prompt,
        )
        return replace(result, sources=sources)

    async def _retrieve(self, user: User, prepared: Prepared) -> tuple[ChunkHit, ...]:
        """Retrieval for a scoped conversation. The scope comes from the stored conversation and is
        re-verified against the owner on every request (D-75, rule 13)."""
        conv = prepared.conversation
        scope: ResolvedScope = await ScopeResolver(self._db).resolve(
            user.id,
            conv.scope_type,
            conv.scope_id,  # type: ignore[arg-type]
        )
        previous = await self._messages.previous_user_message(
            conversation_id=conv.id,
            user_id=user.id,
            before_sequence=prepared.user_message.sequence_number,
        )
        query = build_query(
            prepared.user_message.content, previous.content if previous is not None else None
        )
        searcher = Searcher(self._db, self._settings, make_query_embedder(self._settings))
        result = await searcher.search(scope, query, mode="hybrid")
        return tuple(result.hits)

    def make_request(
        self, prepared: Prepared, system_prompt: str, messages: list[LLMMessage]
    ) -> LLMRequest:
        s = self._settings
        max_output = s.llm_max_output_tokens
        if prepared.model.max_output_tokens:
            max_output = min(max_output, prepared.model.max_output_tokens)
        return LLMRequest(
            model=prepared.model.provider_model_id,
            messages=messages,
            max_output_tokens=max_output,
            system_prompt=system_prompt,
            temperature=prepared.model.default_temperature,
            timeouts=TimeoutPolicy(
                connect=s.llm_connect_timeout_seconds,
                generation=s.llm_generation_timeout_seconds,
                stream_inactivity=s.llm_stream_inactivity_timeout_seconds,
                overall=s.llm_overall_timeout_seconds,
            ),
            thinking_budget=s.llm_thinking_budget,
            request_tag=str(prepared.assistant_message.id),  # opaque, safe to log
        )

    async def build_context_or_fail(
        self, *, user: User, prepared: Prepared, started: float
    ) -> ContextResult:
        """Build the context; if that fails, store the answer as failed before raising, so the
        reserved row never stays pending (used before the first stream event is sent)."""
        try:
            return await self.build_context(user=user, prepared=prepared)
        except asyncio.CancelledError:
            await asyncio.shield(self.finalize_failure(prepared, None, started, status="cancelled"))
            raise
        except LLMError as exc:
            await self.finalize_failure(prepared, exc, started)
            raise
        except AiError as exc:
            await self.finalize_failure(prepared, exc, started, record_usage=False)
            raise
        except Exception:
            error = LLMBadResponseError()
            await self.finalize_failure(prepared, error, started)
            raise error from None

    async def reload_prepared(self, snapshot: Prepared) -> Prepared | None:
        """Re-attach a prepared generation to THIS session (the streaming task has its own).
        Returns None if the conversation was deleted in the meantime."""
        user_id = snapshot.conversation.user_id
        conversation = await self._conversations.get_owned(
            conversation_id=snapshot.conversation.id, user_id=user_id
        )
        assistant = await self._messages.get_owned(
            message_id=snapshot.assistant_message.id, user_id=user_id
        )
        user_message = await self._messages.get_owned(
            message_id=snapshot.user_message.id, user_id=user_id
        )
        catalog_model = await self._catalog.get_model(snapshot.model.internal_id)
        if (
            conversation is None
            or assistant is None
            or user_message is None
            or catalog_model is None
        ):
            return None
        return Prepared(
            conversation=conversation,
            user_message=user_message,
            assistant_message=assistant,
            model=snapshot.model,
            catalog_model=catalog_model,
            system_prompt=snapshot.system_prompt,
            prompt_version=snapshot.prompt_version,
            answer_mode=snapshot.answer_mode,
        )

    async def run_generation(self, *, user: User, prepared: Prepared) -> GenerationResult:
        started = time.monotonic()
        try:
            context = await self.build_context(user=user, prepared=prepared)
            if context.canned_reply is not None:
                return await self.finalize_canned(prepared, context.canned_reply)
            request = self.make_request(prepared, context.system_prompt, context.messages)
            response = await self._call_with_retries(request)
        except asyncio.CancelledError:
            # The client went away. Do not leave a row that looks active (best effort, shielded).
            await asyncio.shield(self.finalize_failure(prepared, None, started, status="cancelled"))
            raise
        except LLMError as exc:
            await self.finalize_failure(prepared, exc, started)
            raise
        except AiError as exc:
            await self.finalize_failure(prepared, exc, started, record_usage=False)
            raise
        except Exception:
            error = LLMBadResponseError()
            await self.finalize_failure(prepared, error, started)
            raise error from None
        return await self.finalize_success(prepared, response, started, sources=context.sources)

    async def _call_with_retries(self, request: LLMRequest) -> LLMResponse:
        """Retry only transient failures, before any output exists (D-50)."""
        provider = self._runtime.provider()
        attempts = 1 + self._settings.llm_max_retries
        for attempt in range(attempts):
            try:
                return await provider.generate(request)
            except LLMError as exc:
                if not exc.retryable or attempt == attempts - 1:
                    raise
                await asyncio.sleep(_backoff_delay(exc, attempt))
        raise LLMBadResponseError()  # unreachable: the loop returns or raises

    async def stream_with_retries(self, request: LLMRequest) -> AsyncIterator[StreamEvent]:
        """Stream from the provider, retrying transient failures ONLY before the first delta.

        Once any text has been produced a retry would duplicate or contradict it, so the error is
        raised instead (D-50). The upstream iterator is always closed, which is what stops the
        provider call when the consumer is cancelled."""
        provider = self._runtime.provider()
        attempts = 1 + self._settings.llm_max_retries
        for attempt in range(attempts):
            produced = False
            iterator = provider.stream(request)
            try:
                async for event in iterator:
                    if isinstance(event, StreamDelta):
                        produced = True
                    yield event
                return
            except LLMError as exc:
                if produced or not exc.retryable or attempt == attempts - 1:
                    raise
                await asyncio.sleep(_backoff_delay(exc, attempt))
            finally:
                closer = getattr(iterator, "aclose", None)
                if closer is not None:
                    with contextlib.suppress(Exception):
                        await closer()

    # ── step 3: store the outcome ────────────────────────────────────────────

    async def finalize_success(
        self,
        prepared: Prepared,
        response: LLMResponse,
        started: float,
        *,
        sources: Sequence[ChunkHit] = (),
    ) -> GenerationResult:
        usage = response.usage
        assistant = prepared.assistant_message
        now = datetime.now(UTC)
        content = response.content
        used: list[int] = []
        if sources:  # the model's [n] markers are never trusted (D-75)
            content, used = validate_citations(content, len(sources))
        assistant.content = content
        assistant.status = "completed"
        assistant.finish_reason = response.finish_reason.value
        assistant.input_tokens = usage.input_tokens
        assistant.output_tokens = usage.output_tokens
        assistant.reasoning_tokens = usage.reasoning_tokens
        assistant.usage_source = usage.source.value
        assistant.completed_at = now
        await self._record_usage(prepared, usage, "success", None, started, response)
        prepared.conversation.last_message_at = now
        citations = await MessageCitationRepository(self._db).add_for_message(
            user_id=prepared.conversation.user_id,
            message_id=assistant.id,
            ranked=[(n, sources[n - 1]) for n in used],
        )
        await self._commit_outcome(prepared, fail_if_gone=True)
        logger.info(
            "ai_generation_completed",
            conversation_id=str(prepared.conversation.id),
            message_id=str(assistant.id),
            model=prepared.model.internal_id,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            finish_reason=response.finish_reason.value,
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        return GenerationResult(
            conversation=prepared.conversation,
            user_message=prepared.user_message,
            assistant_message=assistant,
            usage=usage,
            citations=citations,
        )

    async def finalize_canned(self, prepared: Prepared, reply: str) -> GenerationResult:
        """Fixed insufficient-evidence answer: the model is not called and no usage is recorded."""
        assistant = prepared.assistant_message
        now = datetime.now(UTC)
        assistant.content = reply
        assistant.status = "completed"
        assistant.finish_reason = "insufficient_evidence"
        assistant.usage_source = Usage().source.value
        assistant.completed_at = now
        prepared.conversation.last_message_at = now
        await self._commit_outcome(prepared, fail_if_gone=True)
        logger.info("ai_generation_no_evidence", message_id=str(assistant.id))
        return GenerationResult(
            conversation=prepared.conversation,
            user_message=prepared.user_message,
            assistant_message=assistant,
            usage=Usage(),
        )

    async def finalize_failure(
        self,
        prepared: Prepared,
        error: AiError | None,
        started: float,
        *,
        status: str = "failed",
        record_usage: bool = True,
        usage: Usage | None = None,
        partial_content: str | None = None,
    ) -> None:
        """Mark the answer failed/cancelled so it can never look successful.

        `partial_content` keeps what a stream produced before it stopped. `usage` is only what the
        provider actually reported; otherwise tokens stay NULL and the source `unavailable` (D-40).
        """
        assistant = prepared.assistant_message
        code = error.code if error is not None else None
        usage = usage or Usage()
        assistant.status = status
        assistant.error_code = code
        if partial_content is not None:
            assistant.content = partial_content
        assistant.usage_source = usage.source.value
        if usage.source is not UsageSource.unavailable:
            assistant.input_tokens = usage.input_tokens
            assistant.output_tokens = usage.output_tokens
            assistant.reasoning_tokens = usage.reasoning_tokens
        assistant.completed_at = None
        if record_usage:
            await self._record_usage(
                prepared,
                usage,
                "cancelled" if status == "cancelled" else "failed",
                code,
                started,
                None,
            )
        await self._commit_outcome(prepared, fail_if_gone=False)
        logger.info(
            "ai_generation_failed",
            conversation_id=str(prepared.conversation.id),
            message_id=str(assistant.id),
            model=prepared.model.internal_id,
            status=status,
            error_code=code,
            duration_ms=int((time.monotonic() - started) * 1000),
        )

    async def _commit_outcome(self, prepared: Prepared, *, fail_if_gone: bool) -> None:
        """Commit the outcome. If the user deleted the conversation while the model was working,
        its rows are gone and there is nothing left to update."""
        try:
            await self._db.commit()
        except (IntegrityError, StaleDataError):
            await self._db.rollback()
            logger.info("ai_outcome_dropped", reason="conversation_deleted")
            if fail_if_gone:
                raise ConversationNotFoundError() from None

    async def _record_usage(
        self,
        prepared: Prepared,
        usage: Usage,
        request_status: str,
        error_code: str | None,
        started: float,
        response: LLMResponse | None,
    ) -> None:
        price = find_price(prepared.model.provider, prepared.model.provider_model_id)
        cost = estimate_cost(price, usage)
        await self._usage.add(
            user_id=prepared.conversation.user_id,
            conversation_id=prepared.conversation.id,
            message_id=prepared.assistant_message.id,
            provider_id=prepared.catalog_model.provider_id,
            model_id=prepared.catalog_model.id,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            reasoning_tokens=usage.reasoning_tokens,
            usage_source=usage.source.value,
            estimated_cost=cost,
            currency=price.currency if cost is not None and price is not None else None,
            pricing_version=price.pricing_version
            if cost is not None and price is not None
            else None,
            request_status=request_status,
            error_code=error_code,
            duration_ms=int((time.monotonic() - started) * 1000),
            provider_request_id=response.provider_request_id if response else None,
        )


def _effective_mode(conversation: Conversation, requested: str | None) -> str:
    """General conversations never retrieve; scoped ones default to the strictest mode."""
    if conversation.scope_type == "general":
        return "general"
    return requested or "document_only"


def _prompt_key(mode: str) -> str:
    return {"document_only": DOCUMENT_ONLY_KEY, "document_first": DOCUMENT_FIRST_KEY}.get(
        mode, PROMPT_KEY
    )


def _backoff_delay(exc: LLMError, attempt: int) -> float:
    """Exponential backoff with jitter, honouring Retry-After, capped (D-50)."""
    delay = exc.retry_after or RETRY_BASE_DELAY * (2**attempt)
    return float(min(delay * (1 + random.random() * 0.25), RETRY_MAX_DELAY))  # noqa: S311


def _seconds_until_utc_midnight() -> int:
    now = datetime.now(UTC)
    midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1, int((midnight - now).total_seconds()))
