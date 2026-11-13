"""The extraction run (spec 9.7): one document -> concepts and relationships -> verification ->
graph persistence, executed in the Celery worker only (rule 13, D-84).

Discipline copied from the study engine (D-85, D-86): the job is claimed atomically so a duplicate
delivery does nothing; cancellation is checked between stages and while the provider call is in
flight; provider errors that prove nothing was processed are retried a bounded number of times and
a timeout never is; at most ONE correction call for malformed output; one usage row per provider
attempt (`request_kind = 'extraction'`, so it counts toward the daily quota, D-124); a job is never
marked completed when saving failed. Nothing here logs document text, prompts or model replies.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.errors import (
    AiError,
    LLMContentBlockedError,
    LLMError,
    LLMNotConfiguredError,
    LLMTimeoutError,
)
from app.ai.model_registry import ModelConfig
from app.ai.orchestration.runtime import AiRuntime
from app.ai.prompts import knowledge as prompts
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
from app.knowledge import errors
from app.knowledge.persistence import PersistStats, Placement, persist_graph
from app.knowledge.schemas import ExtractionOutput
from app.knowledge.validation import (
    VerifiedOutput,
    parse_extraction,
    stats_of,
    verify,
)
from app.models.llm_provider import LLMModel
from app.repositories.ai_catalog_repository import AiCatalogRepository
from app.repositories.ai_usage_repository import AiUsageRepository
from app.repositories.knowledge_job_repository import KnowledgeJobRepository
from app.repositories.knowledge_repository import KnowledgeRepository
from app.study.errors import NoSourcesError, SourceTooLargeError, StudyError
from app.study.generators.base import OutputInvalid
from app.study.prompting import build_user_turn, correction_turn
from app.study.schemas import SourceSpec
from app.study.source_reader import SourceBundle, SourceReader, estimate_tokens

logger = structlog.get_logger(__name__)

COMPLETED = "completed"
FAILED = "failed"
CANCELLED = "cancelled"
SKIPPED = "skipped"  # not claimed: already running, finished or cancelled
RETRY_BASE_DELAY = 1.0
RETRY_MAX_DELAY = 20.0
HEARTBEAT_EVERY = 15.0
INPUT_BUDGET_FRACTION = 0.8
PROMPT_OVERHEAD_TOKENS = 400

TASK_BLOCK = """TASK
Extract the academic concepts and the relationships between them from the passages above.
Reply with ONE JSON object of exactly this shape and nothing else:
{
  "concepts": [
    {"name": "...", "type": "concept", "description": "...", "definition": null,
     "aliases": [], "difficulty": null, "confidence": 0.0,
     "evidence": [{"source": 1, "quote": "exact words copied from passage 1"}]}
  ],
  "relationships": [
    {"source": "concept name", "target": "concept name", "type": "PREREQUISITE_OF",
     "statement": "stated", "description": "...", "confidence": 0.0,
     "evidence": [{"source": 1, "quote": "exact words copied from passage 1"}]}
  ]
}
Every quote must be copied word for word from the passage you cite."""


class _Cancelled(Exception):
    pass


class _InvalidOutput(Exception):
    pass


class _NothingVerified(Exception):
    pass


class NoWebSourcesError(Exception):
    """A web run's search returned no usable website (D-144)."""


@dataclass(frozen=True)
class ExtractionDeps:
    session_factory: async_sessionmaker[AsyncSession]
    runtime: AiRuntime


def _now() -> datetime:
    return datetime.now(UTC)


async def run_extraction(
    deps: ExtractionDeps, job_id: Any, celery_task_id: str | None = None
) -> str:
    """Run one job. Returns completed, failed, cancelled or skipped. Job-level failures are
    recorded on the job and never raised; only infrastructure errors propagate."""
    async with deps.session_factory() as db:
        repo = KnowledgeJobRepository(db)
        claimed = await repo.claim(job_id, _now(), celery_task_id)
        await db.commit()
        job = await repo.get(job_id) if claimed else None
    if job is None:
        logger.info("extraction_skipped", job_id=str(job_id))
        return SKIPPED

    run: _Run
    if job.source_kind == "web":
        from app.knowledge.web_extraction import WebRun  # noqa: PLC0415 (circular import)

        run = WebRun(deps, job.id, job.user_id, None)
    else:
        run = _Run(deps, job.id, job.user_id, job.document_id)
    started = time.monotonic()
    outcome, code = FAILED, errors.INTERNAL
    try:
        async with asyncio.timeout(deps.runtime.settings.knowledge_job_timeout_seconds):
            await run.execute()
        outcome, code = COMPLETED, ""
    except _Cancelled:
        outcome, code = CANCELLED, errors.CANCELLED
    except TimeoutError:
        outcome, code = FAILED, errors.TIMEOUT
    except _InvalidOutput:
        outcome, code = FAILED, errors.INVALID_OUTPUT
    except _NothingVerified:
        outcome, code = FAILED, errors.NOTHING_VERIFIED
    except NoWebSourcesError:
        outcome, code = FAILED, errors.NO_WEB_SOURCES
    except SourceTooLargeError:
        outcome, code = FAILED, errors.TOO_LARGE
    except NoSourcesError:
        outcome, code = FAILED, errors.SOURCES_GONE
    except (StudyError, AiError) as exc:
        outcome, code = FAILED, exc.code
    except HTTPException:
        outcome, code = FAILED, errors.SOURCES_GONE  # no longer the user's, or not ready
    except IntegrityError:
        outcome, code = FAILED, errors.SOURCES_GONE  # workspace or document deleted mid-run
    except Exception as exc:  # never leak details: type name only
        if type(exc).__name__ == "SoftTimeLimitExceeded":
            outcome, code = FAILED, errors.TIMEOUT
        else:
            logger.error(
                "extraction_unexpected_error", job_id=str(job_id), error_type=type(exc).__name__
            )
    if outcome != COMPLETED:
        final = await run.finish_unsuccessful(outcome, code)
        if final != outcome:  # lost a race (already cancelled/failed elsewhere): report the truth
            outcome = final
    logger.info(
        "extraction_finished",
        job_id=str(job_id),
        outcome=outcome,
        error_code=code or None,
        duration_ms=int((time.monotonic() - started) * 1000),
    )
    return outcome


class _Run:
    # Subclasses (paper analysis) swap the job table and the usage label; the provider, retry,
    # cancellation and quota machinery below is shared.
    request_kind = "extraction"

    def _jobs(self, db: AsyncSession) -> Any:
        return KnowledgeJobRepository(db)

    task_block = TASK_BLOCK

    def _configured_model(self) -> str:
        return self._s.knowledge_extraction_model

    def __init__(self, deps: ExtractionDeps, job_id: Any, user_id: Any, document_id: Any) -> None:
        self._d = deps
        self._s = deps.runtime.settings
        self._factory = deps.session_factory
        self.job_id = job_id
        self.user_id = user_id
        self.document_id = document_id
        self._last_beat = time.monotonic()

    # main flow ───────────────────────────────────────────────────────────────

    async def execute(self) -> None:
        prompt = active_prompt(prompts.EXTRACT_KEY)
        cfg, catalog = await self._select_model()
        await self._stage(
            "retrieving_sources",
            10,
            model_id=cfg.internal_id,
            prompt_version=f"{prompt.prompt_key}:v{prompt.version}",
        )
        budget = self._input_budget(cfg, prompt.content)
        placement, batches = await self._read_sources(budget)
        await self._checkpoint()

        results: list[VerifiedOutput] = []
        seen_concepts: set[str] = set()
        total = len(batches)
        for i, bundle in enumerate(batches):
            await self._stage("extracting", 15 + int(60 * i / total))
            remaining = self._s.knowledge_max_concepts_per_job - len(seen_concepts)
            if remaining <= 0:
                break
            verified = await self._extract_batch(cfg, catalog, prompt.content, bundle, remaining)
            seen_concepts.update(c.normalised_name for c in verified.concepts)
            results.append(verified)
            await self._checkpoint()

        await self._stage("validating", 80)
        if not any(r.concepts for r in results):
            raise _NothingVerified
        await self._checkpoint()
        await self._stage("saving", 90)
        await self._save(placement, results, total)

    async def _extract_batch(
        self,
        cfg: ModelConfig,
        catalog: LLMModel,
        system_prompt: str,
        bundle: SourceBundle,
        remaining_concepts: int,
    ) -> VerifiedOutput:
        request = self._llm_request(cfg, system_prompt, build_user_turn(bundle.units, TASK_BLOCK))
        schema = ExtractionOutput.model_json_schema()

        def validate(raw: str) -> VerifiedOutput:
            return verify(
                parse_extraction(raw),
                bundle.units,
                max_concepts=remaining_concepts,
                max_relationships=self._s.knowledge_max_relationships_per_job,
            )

        result: VerifiedOutput = await self._validated_call(cfg, catalog, request, schema, validate)
        return result

    def _llm_request(self, cfg: ModelConfig, system_prompt: str, turn: str) -> LLMRequest:
        cap = min(self._s.knowledge_max_output_tokens, cfg.max_output_tokens or 10**9)
        return LLMRequest(
            model=cfg.provider_model_id,
            messages=[LLMMessage(Role.user, turn)],
            max_output_tokens=cap,
            system_prompt=system_prompt,
            temperature=cfg.default_temperature,
            timeouts=TimeoutPolicy(
                connect=self._s.llm_connect_timeout_seconds,
                generation=self._s.llm_generation_timeout_seconds,
                stream_inactivity=self._s.llm_stream_inactivity_timeout_seconds,
                overall=self._s.llm_overall_timeout_seconds,
            ),
            thinking_budget=self._s.llm_thinking_budget
            if cfg.capabilities.thinking_budget
            else None,
            request_tag=str(self.job_id),
        )

    async def _validated_call(
        self,
        cfg: ModelConfig,
        catalog: LLMModel,
        request: LLMRequest,
        schema: dict[str, Any],
        validate: Callable[[str], Any],
    ) -> Any:
        """One provider call, parse and verify, and at most ONE correction call."""
        out_cap = request.max_output_tokens or 1000
        response = await self._call(cfg, catalog, request, schema)
        try:
            return validate(response.content)
        except OutputInvalid as bad:
            logger.info(
                "extraction_output_invalid", job_id=str(self.job_id), problem=str(bad)[:200]
            )
            retry = replace(
                request,
                messages=[
                    *request.messages,
                    LLMMessage(Role.assistant, response.content[: out_cap * 4]),
                    LLMMessage(Role.user, correction_turn(str(bad))),
                ],
            )
            response = await self._call(cfg, catalog, retry, schema)
            try:
                return validate(response.content)
            except OutputInvalid:
                raise _InvalidOutput from None

    # sources ─────────────────────────────────────────────────────────────────

    def _input_budget(self, cfg: ModelConfig, system_prompt: str) -> int:
        limit = self._s.knowledge_max_input_tokens
        if cfg.max_input_tokens:
            limit = min(limit, int(cfg.max_input_tokens * INPUT_BUDGET_FRACTION))
        overhead = PROMPT_OVERHEAD_TOKENS + estimate_tokens(system_prompt + self.task_block)
        return max(200, limit - overhead)

    async def _read_sources(self, budget: int) -> tuple[Placement, list[SourceBundle]]:
        async with self._factory() as db:
            reader = SourceReader(db, self._s)
            # Resolve verifies the document is this user's and has a completed active version;
            # anything else is the same 404 as a missing one.
            source = await reader.resolve(
                self.user_id, SourceSpec(type="document", id=self.document_id)
            )
            estimate = await reader.estimate(source)
            if estimate.tokens <= budget:
                batches = [await reader.read_ordered(source, budget)]
            else:
                batches = await reader.ordered_batches(source, budget)
                if len(batches) > self._s.knowledge_max_batches:
                    raise SourceTooLargeError
            if not batches or not any(b.units for b in batches):
                raise NoSourcesError
            repo = KnowledgeRepository(db)
            version_id = await repo.active_version_id(self.user_id, self.document_id)
            if version_id is None:
                raise NoSourcesError
            await self._jobs(db).update_active(
                self.job_id,
                _now(),
                document_version_id=version_id,
                source_stats={
                    "documents": 1,
                    "units": sum(len(b.units) for b in batches),
                    "estimated_input_tokens": estimate.tokens,
                    "batches": len(batches),
                },
            )
            await db.commit()
        placement = Placement(
            user_id=self.user_id,
            workspace_id=source.workspace_id,
            subject_id=source.subject_id,
            chapter_id=source.chapter_id,
            document_id=self.document_id,
            document_version_id=version_id,
            job_id=self.job_id,
        )
        return placement, batches

    # save / finish ───────────────────────────────────────────────────────────

    async def _save(
        self, placement: Placement, results: list[VerifiedOutput], batches: int
    ) -> None:
        """Persist everything and complete the job in ONE transaction: a failed save leaves no
        half-written graph and the job is never marked completed."""
        totals = PersistStats()
        dropped = {"concepts": 0, "relationships": 0, "definitions": 0}
        async with self._factory() as db:
            for result in results:
                stats = await persist_graph(db, placement, result)
                for name in (
                    "nodes_created",
                    "nodes_matched",
                    "edges_created",
                    "edges_matched",
                    "evidence_added",
                    "candidates_added",
                    "aliases_added",
                    "stale_marked",
                ):
                    setattr(totals, name, getattr(totals, name) + getattr(stats, name))
                for key, value in result.dropped.items():
                    dropped[key] += value
            summary = {
                **totals.as_dict(),
                "batches": batches,
                "verified": [stats_of(r) for r in results],
                "dropped": dropped,
            }
            done = await self._jobs(db).finish(self.job_id, COMPLETED, _now(), result_stats=summary)
            if not done:  # cancelled or failed by the sweeper while we worked: save nothing
                await db.rollback()
                raise _Cancelled
            await db.commit()

    async def finish_unsuccessful(self, outcome: str, code: str) -> str:
        async with self._factory() as db:
            repo = self._jobs(db)
            moved = await repo.finish(self.job_id, outcome, _now(), error_code=code)
            await db.commit()
            if moved:
                return outcome
            job = await repo.get(self.job_id)
            return job.status if job is not None else outcome

    # stages ──────────────────────────────────────────────────────────────────

    async def _stage(self, status: str, progress: int, **extra: Any) -> None:
        async with self._factory() as db:
            ok = await self._jobs(db).set_stage(self.job_id, status, progress, _now(), **extra)
            await db.commit()
        if not ok:  # the sweeper failed it, or it was cancelled out from under us
            raise _Cancelled
        logger.info("extraction_stage", job_id=str(self.job_id), stage=status, progress=progress)

    async def _checkpoint(self) -> None:
        if await self._cancel_requested():
            raise _Cancelled

    async def _cancel_requested(self) -> bool:
        async with self._factory() as db:
            return bool(await self._jobs(db).is_cancel_requested(self.job_id))

    # provider ────────────────────────────────────────────────────────────────

    async def _select_model(self) -> tuple[ModelConfig, LLMModel]:
        registry = self._d.runtime.registry
        if not registry.configured:
            raise LLMNotConfiguredError()
        cfg = registry.resolve(self._configured_model() or None)
        async with self._factory() as db:
            catalog = AiCatalogRepository(db)
            row = await catalog.get_model(cfg.internal_id)
            if row is None:  # first use on a stack whose startup sync could not run (D-58)
                try:
                    await sync_models(db, registry)
                    await db.commit()
                except IntegrityError:
                    await db.rollback()
                row = await catalog.get_model(cfg.internal_id)
            if row is None:
                raise LLMNotConfiguredError()
            return cfg, row

    async def _call(
        self, cfg: ModelConfig, catalog: LLMModel, request: LLMRequest, schema: dict[str, Any]
    ) -> LLMResponse:
        """One logical provider call. Transient failures that prove nothing was processed are
        retried a limited number of times; everything else is final. Each attempt is recorded."""
        attempt = 0
        while True:
            await self._count_call()
            started = time.monotonic()
            try:
                response = await self._await_provider(self._provider_coro(cfg, request, schema))
            except _Cancelled:
                await self._usage(cfg, catalog, Usage(), "cancelled", None, started, None)
                raise
            except LLMError as exc:
                await self._usage(cfg, catalog, Usage(), "failed", exc.code, started, None)
                retriable = exc.retryable and not isinstance(exc, LLMTimeoutError)
                if retriable and attempt < self._s.study_provider_max_retries:
                    attempt += 1
                    delay = exc.retry_after or RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    await asyncio.sleep(min(float(delay), RETRY_MAX_DELAY))
                    await self._checkpoint()
                    continue
                raise
            if response.finish_reason is FinishReason.content_filter:
                await self._usage(
                    cfg,
                    catalog,
                    response.usage,
                    "failed",
                    LLMContentBlockedError.code,
                    started,
                    response,
                )
                raise LLMContentBlockedError
            await self._usage(cfg, catalog, response.usage, "success", None, started, response)
            return response

    def _provider_coro(self, cfg: ModelConfig, request: LLMRequest, schema: dict[str, Any]) -> Any:
        provider = self._d.runtime.provider()
        if cfg.capabilities.structured_output:
            return provider.generate_structured(request, schema)
        return provider.generate(request)

    async def _await_provider(self, coro: Any) -> LLMResponse:
        """Await the provider while polling for cancellation and keeping the heartbeat fresh."""
        task = asyncio.ensure_future(coro)
        poll = self._s.study_cancel_poll_seconds
        try:
            while True:
                done, _ = await asyncio.wait({task}, timeout=poll)
                if done:
                    result: LLMResponse = task.result()
                    return result
                if await self._cancel_requested():
                    task.cancel()
                    with suppress(asyncio.CancelledError, Exception):
                        await task
                    raise _Cancelled
                if time.monotonic() - self._last_beat > HEARTBEAT_EVERY:
                    self._last_beat = time.monotonic()
                    async with self._factory() as db:
                        await self._jobs(db).touch(self.job_id, _now())
                        await db.commit()
        finally:
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError, Exception):
                    await task

    async def _count_call(self) -> None:
        async with self._factory() as db:
            await self._jobs(db).add_provider_call(self.job_id, _now())
            await db.commit()

    async def _usage(
        self,
        cfg: ModelConfig,
        catalog: LLMModel,
        usage: Usage,
        status: str,
        error_code: str | None,
        started: float,
        response: LLMResponse | None,
    ) -> None:
        """One `ai_usage_records` row per provider attempt. Unknown cost stays NULL (D-39)."""
        price = find_price(cfg.provider, cfg.provider_model_id)
        cost = estimate_cost(price, usage)
        async with self._factory() as db:
            await AiUsageRepository(db).add(
                user_id=self.user_id,
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
                request_kind=self.request_kind,
                request_status=status,
                error_code=error_code,
                duration_ms=int((time.monotonic() - started) * 1000),
                provider_request_id=response.provider_request_id if response else None,
            )
            await db.commit()
