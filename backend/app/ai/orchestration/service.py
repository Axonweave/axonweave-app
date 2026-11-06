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
import re
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from app.ai.errors import (
    AiError,
    AiQuotaExceededError,
    ConversationArchivedError,
    ConversationNotFoundError,
    GenerationInProgressError,
    InputTooLongError,
    LLMBadResponseError,
    LLMError,
    LLMNotConfiguredError,
    StreamingNotAvailableError,
)
from app.ai.model_registry import ModelConfig
from app.ai.orchestration.context import (
    ContextManager,
    ContextRequest,
    ContextResult,
    ConversationHistory,
)
from app.ai.orchestration.runtime import AiRuntime
from app.ai.prompts.registry import active_prompt
from app.ai.sync import sync_models
from app.ai.types import (
    LLMMessage,
    LLMRequest,
    LLMResponse,
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
from app.models.user import User
from app.repositories.ai_catalog_repository import AiCatalogRepository
from app.repositories.ai_conversation_repository import AiConversationRepository
from app.repositories.ai_message_repository import AiMessageRepository
from app.repositories.ai_usage_repository import AiUsageRepository

logger = get_logger(__name__)

PROMPT_KEY = "academic_tutor"
TITLE_MAX_CHARS = 60
RETRY_BASE_DELAY = 0.5  # seconds; doubled per attempt, capped at RETRY_MAX_DELAY
RETRY_MAX_DELAY = 4.0
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


@dataclass
class GenerationResult:
    conversation: Conversation
    user_message: Message
    assistant_message: Message
    usage: Usage


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

    # ── public entry point ───────────────────────────────────────────────────

    async def send_message(
        self,
        *,
        user: User,
        conversation_id: uuid.UUID,
        content: str,
        model_id: str | None,
        stream: bool,
    ) -> GenerationResult:
        if stream:
            # Streaming arrives in M3; the request field already exists so the contract is stable.
            raise StreamingNotAvailableError()
        prepared = await self.prepare(
            user=user, conversation_id=conversation_id, content=content, model_id=model_id
        )
        return await self.run_generation(user=user, prepared=prepared)

    # ── step 1: validate, authorise, reserve ─────────────────────────────────

    async def prepare(
        self, *, user: User, conversation_id: uuid.UUID, content: str, model_id: str | None
    ) -> Prepared:
        # Ownership first: a conversation that is not yours does not exist (rule 2).
        conversation = await self._conversations.get_owned(
            conversation_id=conversation_id, user_id=user.id
        )
        if conversation is None:
            raise ConversationNotFoundError()
        if conversation.status == "archived":
            raise ConversationArchivedError()

        model = self._runtime.registry.resolve(model_id or conversation.model_id)
        if len(content) > self._settings.llm_max_input_chars:
            raise InputTooLongError()

        await self._enforce_limits(user.id)
        catalog_model = await self._catalog_model(model)
        prompt = active_prompt(PROMPT_KEY)

        # Transaction A: short, row-locked. User first, then conversation, always in that order.
        await self._conversations.lock_user(user.id)
        if await self._conversations.count_active_generations(user.id) >= (
            self._settings.ai_max_active_generations_per_user
        ):
            await self._db.rollback()
            raise GenerationInProgressError()
        locked = await self._conversations.get_owned(
            conversation_id=conversation_id, user_id=user.id, for_update=True
        )
        if locked is None:  # deleted while we waited for the lock
            await self._db.rollback()
            raise ConversationNotFoundError()
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
            assistant_message = await self._messages.add(
                conversation_id=locked.id,
                user_id=user.id,
                role="assistant",
                status="pending",
                sequence_number=sequence + 1,
                content="",
                model_id=model.internal_id,
                prompt_key=prompt.prompt_key,
                prompt_version=prompt.version,
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
        )

    async def _enforce_limits(self, user_id: uuid.UUID) -> None:
        s = self._settings
        try:
            await self._limiter.check(f"ai:user:{user_id}", s.ai_requests_per_minute_per_user, 60)
        except HTTPException:
            raise AiQuotaExceededError(retry_after=60) from None
        reset_in = _seconds_until_utc_midnight()
        if await self._usage.messages_today(user_id) >= s.ai_daily_message_quota:
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
        provider = self._runtime.provider()
        model = prepared.model
        settings = self._settings
        budget = (model.max_input_tokens or settings.llm_fallback_input_tokens) - (
            settings.llm_max_output_tokens
        )

        async def counter(system: str, messages: list[LLMMessage]) -> int | None:
            if not model.capabilities.count_tokens:
                return None
            probe = self._request(prepared, system, messages)
            return await provider.count_tokens(probe)

        manager = ContextManager(
            [ConversationHistory(self._messages, limit=settings.llm_history_limit)],
            budget_tokens=max(budget, 1),
            counter=counter,
        )
        return await manager.build(
            ContextRequest(
                conversation_id=prepared.conversation.id,
                user_id=user.id,
                new_message=prepared.user_message.content,
                before_sequence=prepared.user_message.sequence_number,
            ),
            system_prompt=prepared.system_prompt,
        )

    def _request(
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

    async def run_generation(self, *, user: User, prepared: Prepared) -> GenerationResult:
        started = time.monotonic()
        try:
            context = await self.build_context(user=user, prepared=prepared)
            request = self._request(prepared, context.system_prompt, context.messages)
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
        return await self.finalize_success(prepared, response, started)

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
                delay = exc.retry_after or RETRY_BASE_DELAY * (2**attempt)
                await asyncio.sleep(min(delay, RETRY_MAX_DELAY))
        raise LLMBadResponseError()  # unreachable: the loop returns or raises

    # ── step 3: store the outcome ────────────────────────────────────────────

    async def finalize_success(
        self, prepared: Prepared, response: LLMResponse, started: float
    ) -> GenerationResult:
        usage = response.usage
        assistant = prepared.assistant_message
        now = datetime.now(UTC)
        assistant.content = response.content
        assistant.status = "completed"
        assistant.finish_reason = response.finish_reason.value
        assistant.input_tokens = usage.input_tokens
        assistant.output_tokens = usage.output_tokens
        assistant.reasoning_tokens = usage.reasoning_tokens
        assistant.usage_source = usage.source.value
        assistant.completed_at = now
        await self._record_usage(prepared, usage, "success", None, started, response)
        prepared.conversation.last_message_at = now
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
        )

    async def finalize_failure(
        self,
        prepared: Prepared,
        error: AiError | None,
        started: float,
        *,
        status: str = "failed",
        record_usage: bool = True,
    ) -> None:
        """Mark the answer failed/cancelled so it can never look successful."""
        assistant = prepared.assistant_message
        code = error.code if error is not None else None
        assistant.status = status
        assistant.error_code = code
        assistant.usage_source = UsageSource.unavailable.value
        assistant.completed_at = None
        if record_usage:
            await self._record_usage(
                prepared,
                Usage(),
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


def _seconds_until_utc_midnight() -> int:
    now = datetime.now(UTC)
    midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1, int((midnight - now).total_seconds()))
