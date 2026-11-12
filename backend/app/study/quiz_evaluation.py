"""AI-assisted grading of short-answer and descriptive quiz answers (Phase 5 M1, D-112).

Runs through the existing provider layer only. Rules:

* The answer key is read inside this module and never returned; only the grade, a short explanation
  and the missing points the grader model wrote are stored on the answer row.
* One provider call per answer plus at most ONE correction call. Never a loop.
* A failure never becomes a silent 0: the answer stays `pending` (retryable) or becomes `failed`
  (the model returned unusable output twice; also retryable).
* Each answer row is locked (`FOR UPDATE SKIP LOCKED`) only while its own provider call runs, so a
  concurrent retry skips rows that are being graded and nothing is graded twice. The attempt row
  is not held.
* Every call writes an `ai_usage_records` row with request_kind="evaluation" (unknown cost is NULL).
* Rate limits and the daily token quota apply. Student text, the key and model output are never
  logged: ids, codes, counts and durations only.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime

import structlog
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.errors import (
    LLMContentBlockedError,
    LLMError,
    LLMNotConfiguredError,
    LLMRateLimitedError,
)
from app.ai.model_registry import ModelConfig
from app.ai.orchestration.runtime import AiRuntime
from app.ai.prompts.registry import active_prompt
from app.ai.sync import sync_models
from app.ai.types import (
    FinishReason,
    LLMMessage,
    LLMRequest,
    LLMResponse,
    Role,
    TimeoutPolicy,
    Usage,
)
from app.ai.usage.pricing import estimate_cost, find_price
from app.core.rate_limit import get_rate_limiter
from app.models.llm_provider import LLMModel
from app.models.quiz import QuizAttemptAnswer, QuizQuestion
from app.repositories.ai_catalog_repository import AiCatalogRepository
from app.repositories.ai_usage_repository import AiUsageRepository
from app.study.answer_grader import (
    GRADE_SCHEMA,
    GradeResult,
    grading_turn,
    parse_grade,
)
from app.study.errors import EvaluationRateLimitedError, EvaluationUnavailableError
from app.study.generators.base import OutputInvalid
from app.study.prompting import correction_turn
from app.study.quiz_scoring import AI_CORRECT_THRESHOLD, money

logger = structlog.get_logger()

MAX_INLINE_EVALUATIONS = 10
INVALID_OUTPUT = "EVALUATION_OUTPUT_INVALID"
_STOP_CODES = {LLMNotConfiguredError.code, LLMRateLimitedError.code}


@dataclass
class EvaluationRun:
    graded: int = 0
    pending: int = 0
    failed: int = 0
    stopped: bool = False  # a provider-wide problem ended the run early


class QuizEvaluator:
    def __init__(self, db: AsyncSession, runtime: AiRuntime) -> None:
        self._db = db
        self._runtime = runtime
        self._s = runtime.settings

    @property
    def available(self) -> bool:
        return bool(self._s.quiz_ai_grading_enabled and self._runtime.registry.configured)

    # limits ──────────────────────────────────────────────────────────────────

    async def enforce_limits(self, user_id: uuid.UUID) -> None:
        try:
            await get_rate_limiter().check(
                f"quizeval:user:{user_id}", self._s.quiz_evaluations_per_minute_per_user, 60
            )
        except HTTPException:
            raise EvaluationRateLimitedError from None
        used = await AiUsageRepository(self._db).tokens_today(user_id)
        if used >= self._s.ai_daily_token_quota:
            raise EvaluationUnavailableError

    # model ───────────────────────────────────────────────────────────────────

    async def _model(self) -> tuple[ModelConfig, LLMModel]:
        registry = self._runtime.registry
        if not registry.configured:
            raise LLMNotConfiguredError()
        cfg = registry.resolve(self._s.study_generation_model or None)
        catalog = AiCatalogRepository(self._db)
        row = await catalog.get_model(cfg.internal_id)
        if row is None:  # first use on a stack whose startup sync could not run (D-58)
            try:
                await sync_models(self._db, registry)
                await self._db.commit()
            except IntegrityError:
                await self._db.rollback()
            row = await catalog.get_model(cfg.internal_id)
        if row is None:
            raise LLMNotConfiguredError()
        return cfg, row

    def _request(self, cfg: ModelConfig, system_prompt: str, turn: str, tag: str) -> LLMRequest:
        s = self._s
        return LLMRequest(
            model=cfg.provider_model_id,
            messages=[LLMMessage(Role.user, turn)],
            max_output_tokens=s.quiz_grading_max_output_tokens,
            system_prompt=system_prompt,
            temperature=0.0,
            timeouts=TimeoutPolicy(
                connect=s.llm_connect_timeout_seconds,
                generation=s.llm_generation_timeout_seconds,
                stream_inactivity=s.llm_stream_inactivity_timeout_seconds,
                overall=s.llm_overall_timeout_seconds,
            ),
            thinking_budget=s.llm_thinking_budget if cfg.capabilities.thinking_budget else None,
            request_tag=tag,
        )

    async def _call(
        self,
        user_id: uuid.UUID,
        cfg: ModelConfig,
        catalog: LLMModel,
        request: LLMRequest,
    ) -> LLMResponse:
        started = time.monotonic()
        provider = self._runtime.provider()
        usage_repo = AiUsageRepository(self._db)
        price = find_price(cfg.provider, cfg.provider_model_id)

        async def record(usage: Usage, status: str, code: str | None, rid: str | None) -> None:
            cost = estimate_cost(price, usage)
            await usage_repo.add(
                user_id=user_id,
                provider_id=catalog.provider_id,
                model_id=catalog.id,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                reasoning_tokens=usage.reasoning_tokens,
                usage_source=usage.source.value,
                estimated_cost=cost,
                currency=price.currency if cost is not None and price is not None else None,
                pricing_version=price.pricing_version
                if cost is not None and price is not None
                else None,
                request_kind="evaluation",
                request_status=status,
                error_code=code,
                duration_ms=int((time.monotonic() - started) * 1000),
                provider_request_id=rid,
            )

        try:
            if cfg.capabilities.structured_output:
                response = await provider.generate_structured(request, GRADE_SCHEMA)
            else:
                response = await provider.generate(request)
        except LLMError as exc:
            await record(Usage(), "failed", exc.code, None)
            raise
        if response.finish_reason is FinishReason.content_filter:
            await record(response.usage, "failed", LLMContentBlockedError.code, None)
            raise LLMContentBlockedError
        await record(response.usage, "success", None, response.provider_request_id)
        return response

    async def grade(
        self, user_id: uuid.UUID, question: QuizQuestion, answer: str, tag: str
    ) -> GradeResult:
        """One graded answer: a provider call, validation, and at most one correction call.
        Raises LLMError (provider problem) or OutputInvalid (unusable output twice)."""
        cfg, catalog = await self._model()
        system_prompt = active_prompt("study_quiz_grading").content
        request = self._request(cfg, system_prompt, grading_turn(question, answer), tag)
        response = await self._call(user_id, cfg, catalog, request)
        try:
            return parse_grade(response.content)
        except OutputInvalid as bad:
            logger.info("quiz_grade_output_invalid", question_id=str(question.id))
            retry = replace(
                request,
                messages=[
                    *request.messages,
                    LLMMessage(Role.assistant, response.content[:2000]),
                    LLMMessage(Role.user, correction_turn(str(bad))),
                ],
            )
            response = await self._call(user_id, cfg, catalog, retry)
            return parse_grade(response.content)  # a second OutputInvalid propagates

    # run ─────────────────────────────────────────────────────────────────────

    async def _lock_row(self, row_id: uuid.UUID, user_id: uuid.UUID) -> QuizAttemptAnswer | None:
        stmt = (
            select(QuizAttemptAnswer)
            .where(
                QuizAttemptAnswer.id == row_id,
                QuizAttemptAnswer.user_id == user_id,
                QuizAttemptAnswer.evaluation_status.in_(("pending", "failed")),
            )
            .with_for_update(skip_locked=True)
        )
        return (await self._db.execute(stmt)).scalar_one_or_none()

    async def evaluate(
        self,
        user_id: uuid.UUID,
        questions: dict[uuid.UUID, QuizQuestion],
        row_ids: list[uuid.UUID],
        *,
        limit: int = MAX_INLINE_EVALUATIONS,
    ) -> EvaluationRun:
        """Grade up to `limit` waiting answers. Commits after each one."""
        run = EvaluationRun()
        for row_id in row_ids[:limit]:
            row = await self._lock_row(row_id, user_id)
            if row is None:  # graded meanwhile or being graded by a concurrent request
                await self._db.commit()
                continue
            question = questions.get(row.question_id)
            answer = row.submitted_answer
            if question is None or not isinstance(answer, str) or not answer.strip():
                await self._db.commit()
                continue
            try:
                result = await self.grade(user_id, question, answer, str(row.attempt_id))
            except OutputInvalid:
                row.evaluation_status = "failed"
                row.evaluation_error_code = INVALID_OUTPUT
                run.failed += 1
            except LLMError as exc:
                row.evaluation_status = "pending"
                row.evaluation_error_code = exc.code
                run.pending += 1
                if exc.code in _STOP_CODES:
                    await self._db.commit()
                    run.stopped = True
                    break
            else:
                row.evaluation_status = "graded"
                row.evaluation_error_code = None
                row.awarded_score = money(result.fraction * float(row.max_score))
                row.is_correct = result.fraction >= AI_CORRECT_THRESHOLD
                row.feedback = result.explanation or None
                row.evaluation_detail = result.detail()
                row.ai_assisted = True
                row.grading_method = "ai"
                row.evaluated_at = datetime.now(UTC)
                run.graded += 1
            await self._db.commit()
        logger.info(
            "quiz_evaluation_run", graded=run.graded, pending=run.pending, failed=run.failed
        )
        return run
