"""The generation engine: runs one `generation_jobs` row from pending to a terminal state.

Pipeline (spec 4.1, steps 4 to 12), each stage in its own short transaction so no database
transaction is held open while the provider works:

    claim -> select model -> read sources (retrieving_sources) -> build prompt -> provider call
    (generating) -> parse and validate, at most ONE correction call (validating) -> save (saving)

Safety rules enforced here, all covered by tests:
* The job is claimed with an atomic pending -> retrieving_sources update. A redelivered Celery
  message or a duplicate dispatch finds the job already claimed and does nothing, so an expensive
  generation whose outcome is uncertain is never restarted (D-88).
* Provider calls are retried only for errors that prove the request was not processed (busy,
  unavailable). A timeout is NOT retried: the provider may already have run and billed it.
* Total provider calls per job: 1 (+ transient retries) + at most 1 correction. Never a loop.
* Every call writes an `ai_usage_records` row with request_kind="generation" (honest, NULL if
  unknown). Source text, prompts and model output are never logged or stored in errors; failures
  keep a safe code only.
* A cancel request is honoured between stages and while the provider call is in flight.
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
from app.models.llm_provider import LLMModel
from app.repositories.ai_catalog_repository import AiCatalogRepository
from app.repositories.ai_usage_repository import AiUsageRepository
from app.repositories.flashcard_repository import FlashcardRepository
from app.repositories.generation_job_repository import GenerationJobRepository
from app.repositories.quiz_repository import QuizRepository
from app.repositories.study_material_repository import StudyMaterialRepository
from app.retrieval.searcher import QueryEmbedder
from app.study import errors
from app.study.errors import (
    NoSourcesError,
    SourceTooLargeError,
    SourceTooSmallError,
    StudyError,
)
from app.study.flashcard_rows import generated_card_rows
from app.study.generators.base import Generator, GeneratorSettings, OutputInvalid
from app.study.generators.registry import get_generator, validate_settings
from app.study.prompting import (
    build_notes_turn,
    build_user_turn,
    correction_turn,
    source_refs_for,
)
from app.study.quiz_rows import generated_question_rows
from app.study.schemas import GenerationRequest
from app.study.source_reader import (
    ResolvedSource,
    SourceBundle,
    SourceReader,
    estimate_tokens,
)
from app.study.validation import Note, parse_notes, validate_output

logger = structlog.get_logger(__name__)

COMPLETED = "completed"
FAILED = "failed"
CANCELLED = "cancelled"
SKIPPED = "skipped"  # not claimed: already running, finished or cancelled
RETRY_BASE_DELAY = 1.0
RETRY_MAX_DELAY = 20.0
HEARTBEAT_EVERY = 15.0
INPUT_BUDGET_FRACTION = 0.8  # of a model's verified input limit
PROMPT_OVERHEAD_TOKENS = 300
CONTENT_SCHEMA_VERSION = 1
MAX_MAP_BATCHES = 30
MAX_CONDENSE_ROUNDS = 3


class _Cancelled(Exception):
    """Internal: the user cancelled the job."""


class _InvalidOutput(Exception):
    """Internal: the output was still invalid after the one correction attempt."""


@dataclass(frozen=True)
class EngineDeps:
    session_factory: async_sessionmaker[AsyncSession]
    runtime: AiRuntime
    embedder: QueryEmbedder | None = None


def _now() -> datetime:
    return datetime.now(UTC)


def redact_request(request: dict[str, Any]) -> dict[str, Any]:
    """A pasted text source is held only until it has been read; then it is removed (D-82)."""
    source = dict(request.get("source") or {})
    if source.get("text") is not None:
        source["text"] = None
        source["redacted"] = True
    return {**request, "source": source}


def coverage_report(bundle: SourceBundle, batch_count: int) -> dict[str, Any]:
    """Which sources the result is based on: counts and document ids, never text (spec 5.5)."""
    per_doc: dict[str, dict[str, Any]] = {}
    for unit in bundle.units:
        if unit.document_id is None:
            continue
        entry = per_doc.setdefault(
            str(unit.document_id),
            {"document_id": str(unit.document_id), "name": unit.document_name, "chunks": 0},
        )
        entry["chunks"] += 1
    return {
        "mode": bundle.mode,
        "batches": batch_count,
        "units_included": len(bundle.units),
        "units_available": bundle.units_available,
        "complete": not bundle.truncated and bundle.mode in ("ordered", "text"),
        "documents": list(per_doc.values()),
    }


async def run_generation(deps: EngineDeps, job_id: Any, celery_task_id: str | None = None) -> str:
    """Run one job. Returns completed, failed, cancelled or skipped. Never raises for job-level
    failures (they are recorded on the job); only infrastructure errors outside it propagate."""
    async with deps.session_factory() as db:
        repo = GenerationJobRepository(db)
        claimed = await repo.claim(job_id, _now(), celery_task_id)
        await db.commit()
        job = await repo.get(job_id) if claimed else None
    if job is None:
        logger.info("generation_skipped", job_id=str(job_id))
        return SKIPPED

    run = _Run(deps, job_id, job.user_id, dict(job.request), job.generation_type)
    started = time.monotonic()
    outcome, code = FAILED, errors.INTERNAL
    try:
        async with asyncio.timeout(deps.runtime.settings.study_job_timeout_seconds):
            await run.execute()
        outcome, code = COMPLETED, ""
    except _Cancelled:
        outcome, code = CANCELLED, errors.CANCELLED
    except TimeoutError:
        outcome, code = FAILED, errors.TIMEOUT
    except _InvalidOutput:
        outcome, code = FAILED, errors.INVALID_OUTPUT
    except (StudyError, AiError) as exc:
        outcome, code = FAILED, exc.code
    except HTTPException:
        outcome, code = FAILED, errors.SOURCES_GONE  # a source stopped being the user's or ready
    except IntegrityError:
        outcome, code = FAILED, errors.SOURCES_GONE  # workspace or subject deleted mid-run
    except Exception as exc:  # never leak details: type name only
        if type(exc).__name__ == "SoftTimeLimitExceeded":
            outcome, code = FAILED, errors.TIMEOUT
        else:
            logger.error(
                "generation_unexpected_error", job_id=str(job_id), error_type=type(exc).__name__
            )
    if outcome != COMPLETED:
        final = await run.finish_unsuccessful(outcome, code)
        if final != outcome:  # lost a race (already cancelled/failed elsewhere): report truth
            outcome = final
    logger.info(
        "generation_finished",
        job_id=str(job_id),
        outcome=outcome,
        error_code=code or None,
        duration_ms=int((time.monotonic() - started) * 1000),
    )
    return outcome


class _Run:
    def __init__(
        self,
        deps: EngineDeps,
        job_id: Any,
        user_id: Any,
        request: dict[str, Any],
        generation_type: str,
    ) -> None:
        self._d = deps
        self._s = deps.runtime.settings
        self._factory = deps.session_factory
        self.job_id = job_id
        self.user_id = user_id
        self._raw_request = request
        self._generation_type = generation_type
        self._last_beat = time.monotonic()

    # main flow ───────────────────────────────────────────────────────────────

    async def execute(self) -> None:
        raw = dict(self._raw_request)
        regen = raw.pop("regenerate", None)  # internal: set by the service, never by the client
        request = GenerationRequest.model_validate(raw)
        generator = get_generator(request.generation_type, self._s)
        gsettings = validate_settings(generator, request.settings)
        prompt = active_prompt(generator.prompt_key)
        heading = str(regen["heading"]) if regen and regen.get("heading") else None

        cfg, catalog = await self._select_model()
        await self._stage(
            "retrieving_sources",
            10,
            model_id=cfg.internal_id,
            prompt_version=f"{prompt.prompt_key}:v{prompt.version}",
        )
        instruction = (
            generator.section_instruction(gsettings, heading)
            if heading
            else generator.instruction(gsettings)
        )
        budget = self._input_budget(cfg, prompt.content, instruction)
        source, bundle, batches = await self._read_sources(
            request, generator, gsettings, budget, heading
        )
        await self._checkpoint()

        if batches:
            output = await self._map_reduce(generator, gsettings, batches, cfg, catalog, budget)
        else:
            llm_request = self._llm_request(
                cfg, prompt.content, build_user_turn(bundle.units, instruction), generator
            )
            await self._stage("generating", 30)
            output = await self._validated_call(
                cfg,
                catalog,
                llm_request,
                generator.output_model.model_json_schema(),
                lambda text: validate_output(generator, text, gsettings, len(bundle.units)),
            )

        await self._checkpoint()
        await self._stage("saving", 92)
        await self._save(
            request,
            generator,
            gsettings,
            source,
            bundle,
            output,
            cfg,
            prompt.version,
            regen,
            len(batches) if batches else 1,
        )

    def _llm_request(
        self, cfg: ModelConfig, system_prompt: str, turn: str, generator: Generator
    ) -> LLMRequest:
        return LLMRequest(
            model=cfg.provider_model_id,
            messages=[LLMMessage(Role.user, turn)],
            max_output_tokens=self._output_cap(generator, cfg),
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
        llm_request: LLMRequest,
        schema: dict[str, Any],
        validate: Callable[[str], Any],
    ) -> Any:
        """One provider call, parse and validate, and at most ONE correction call."""
        out_cap = llm_request.max_output_tokens or 1000
        response = await self._call(cfg, catalog, llm_request, schema)
        await self._stage("validating", 65)
        try:
            return validate(response.content)
        except OutputInvalid as bad:
            logger.info(
                "generation_output_invalid", job_id=str(self.job_id), problem=str(bad)[:200]
            )
            await self._stage("generating", 70)
            retry_request = replace(
                llm_request,
                messages=[
                    *llm_request.messages,
                    LLMMessage(Role.assistant, response.content[: out_cap * 4]),
                    LLMMessage(Role.user, correction_turn(str(bad))),
                ],
            )
            response = await self._call(cfg, catalog, retry_request, schema)
            await self._stage("validating", 85)
            try:
                return validate(response.content)
            except OutputInvalid:
                raise _InvalidOutput from None

    # map-reduce (D-91) ───────────────────────────────────────────────────────

    async def _notes_step(
        self,
        generator: Generator,
        gsettings: GeneratorSettings,
        turn: str,
        allowed: set[int],
        cfg: ModelConfig,
        catalog: LLMModel,
    ) -> list[Note]:
        notes_model = generator.notes_model
        assert notes_model is not None
        request = self._llm_request(
            cfg, active_prompt(generator.notes_prompt_key).content, turn, generator
        )
        result: list[Note] = await self._validated_call(
            cfg,
            catalog,
            request,
            notes_model.model_json_schema(),
            lambda text: parse_notes(notes_model, text, allowed),
        )
        return result

    async def _map_reduce(
        self,
        generator: Generator,
        gsettings: GeneratorSettings,
        batches: list[SourceBundle],
        cfg: ModelConfig,
        catalog: LLMModel,
        budget: int,
    ) -> Any:
        """Ordered map-reduce: every batch, in reading order, is condensed into notes; the notes of
        ALL batches (condensed further only when they would not fit) go to one reducer call."""
        total_units = sum(len(b.units) for b in batches)
        notes: list[Note] = []
        offset = 0
        for i, batch in enumerate(batches):
            await self._checkpoint()
            await self._stage("generating", 20 + int(40 * i / len(batches)))
            allowed = set(range(offset + 1, offset + len(batch.units) + 1))
            turn = build_user_turn(
                batch.units, generator.notes_instruction(gsettings), start=offset + 1
            )
            notes += await self._notes_step(generator, gsettings, turn, allowed, cfg, catalog)
            offset += len(batch.units)

        for _ in range(MAX_CONDENSE_ROUNDS):
            if sum(estimate_tokens(t) for t, _ in notes) <= budget:
                break
            notes = await self._condense(generator, gsettings, notes, cfg, catalog, budget)
        if sum(estimate_tokens(t) for t, _ in notes) > budget:
            raise SourceTooLargeError()

        await self._checkpoint()
        await self._stage("generating", 62)
        turn = build_notes_turn(notes, generator.reduce_instruction(gsettings))
        request = self._llm_request(
            cfg, active_prompt(generator.prompt_key).content, turn, generator
        )
        return await self._validated_call(
            cfg,
            catalog,
            request,
            generator.output_model.model_json_schema(),
            lambda text: validate_output(generator, text, gsettings, total_units),
        )

    async def _condense(
        self,
        generator: Generator,
        gsettings: GeneratorSettings,
        notes: list[Note],
        cfg: ModelConfig,
        catalog: LLMModel,
        budget: int,
    ) -> list[Note]:
        groups: list[list[Note]] = [[]]
        spent = 0
        for note in notes:
            size = estimate_tokens(note[0])
            if groups[-1] and spent + size > budget:
                groups.append([])
                spent = 0
            groups[-1].append(note)
            spent += size
        out: list[Note] = []
        for group in groups:
            await self._checkpoint()
            allowed = {r for _, refs in group for r in refs}
            turn = build_notes_turn(group, generator.notes_instruction(gsettings))
            out += await self._notes_step(generator, gsettings, turn, allowed, cfg, catalog)
        return out

    # stages ──────────────────────────────────────────────────────────────────

    async def _stage(self, status: str, progress: int, **extra: Any) -> None:
        async with self._factory() as db:
            ok = await GenerationJobRepository(db).set_stage(
                self.job_id, status, progress, _now(), **extra
            )
            await db.commit()
        if not ok:  # the sweeper failed it, or it was cancelled out from under us
            raise _Cancelled
        logger.info("generation_stage", job_id=str(self.job_id), stage=status, progress=progress)

    async def _checkpoint(self) -> None:
        if await self._cancel_requested():
            raise _Cancelled

    async def _cancel_requested(self) -> bool:
        async with self._factory() as db:
            return await GenerationJobRepository(db).is_cancel_requested(self.job_id)

    async def _select_model(self) -> tuple[ModelConfig, LLMModel]:
        registry = self._d.runtime.registry
        if not registry.configured:
            raise LLMNotConfiguredError()
        cfg = registry.resolve(self._s.study_generation_model or None)
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

    def _input_budget(self, cfg: ModelConfig, system_prompt: str, instruction: str) -> int:
        limit = self._s.study_max_input_tokens
        if cfg.max_input_tokens:
            limit = min(limit, int(cfg.max_input_tokens * INPUT_BUDGET_FRACTION))
        overhead = PROMPT_OVERHEAD_TOKENS + estimate_tokens(system_prompt + instruction)
        return max(200, limit - overhead)

    def _output_cap(self, generator: Generator, cfg: ModelConfig) -> int:
        cap = min(generator.max_output_tokens or 10**9, self._s.study_max_output_tokens)
        if cfg.max_output_tokens:
            cap = min(cap, cfg.max_output_tokens)
        return cap

    async def _read_sources(
        self,
        request: GenerationRequest,
        generator: Generator,
        gsettings: GeneratorSettings,
        budget: int,
        section_heading: str | None = None,
    ) -> tuple[ResolvedSource, SourceBundle, list[SourceBundle] | None]:
        batches: list[SourceBundle] | None = None
        async with self._factory() as db:
            reader = SourceReader(db, self._s, self._d.embedder)
            source = await reader.resolve(self.user_id, request.source)
            estimate = await reader.estimate(source)
            if source.text is not None:
                bundle = await reader.read_ordered(source, budget)
            elif section_heading:  # regenerate one section: only the passages about it
                try:
                    bundle = await reader.read_retrieved(source, section_heading, budget)
                except NoSourcesError:  # the heading matches nothing: use an even sample instead
                    bundle = await reader.read_sampled(source, budget)
            elif generator.source_mode == "sampled":
                bundle = await reader.read_sampled(source, budget)
            elif generator.source_mode == "retrieved":
                bundle = await reader.read_retrieved(
                    source, generator.retrieval_query(gsettings), budget
                )
            elif estimate.tokens <= budget:
                bundle = await reader.read_ordered(source, budget)
            elif generator.map_reduce:
                batches = await reader.ordered_batches(source, budget)
                if len(batches) > MAX_MAP_BATCHES:
                    raise SourceTooLargeError()
                first = batches[0]
                bundle = SourceBundle(
                    tuple(u for b in batches for u in b.units),
                    "ordered",
                    first.units_available,
                    first.tokens_available,
                )
            elif generator.allow_sampled_fallback:
                bundle = await reader.read_sampled(source, budget)
            else:
                raise SourceTooLargeError()
            if not bundle.units:
                raise NoSourcesError()
            if not section_heading and bundle.tokens < generator.min_source_tokens:
                raise SourceTooSmallError()
            jobs = GenerationJobRepository(db)
            stats = {
                **bundle.stats(),
                "documents": estimate.documents,
                "estimated_input_tokens": bundle.tokens,
                "batches": len(batches) if batches else 1,
            }
            await jobs.update_active(
                self.job_id, _now(), source_stats=stats, request=redact_request(self._raw_request)
            )
            await db.commit()
        return source, bundle, batches

    # provider ────────────────────────────────────────────────────────────────

    async def _call(
        self, cfg: ModelConfig, catalog: LLMModel, request: LLMRequest, schema: dict[str, Any]
    ) -> LLMResponse:
        """One logical provider call: transient failures that prove nothing was processed are
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
                        await GenerationJobRepository(db).touch(self.job_id, _now())
                        await db.commit()
        finally:
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError, Exception):
                    await task

    async def _count_call(self) -> None:
        async with self._factory() as db:
            await GenerationJobRepository(db).add_provider_call(self.job_id, _now())
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
                request_kind="generation",
                request_status=status,
                error_code=error_code,
                duration_ms=int((time.monotonic() - started) * 1000),
                provider_request_id=response.provider_request_id if response else None,
            )
            await db.commit()

    # save / finish ───────────────────────────────────────────────────────────

    async def _save(
        self,
        request: GenerationRequest,
        generator: Generator,
        gsettings: GeneratorSettings,
        source: ResolvedSource,
        bundle: SourceBundle,
        output: Any,
        cfg: ModelConfig,
        prompt_version: int,
        regen: dict[str, Any] | None,
        batch_count: int,
    ) -> None:
        content = {
            "schema_version": CONTENT_SCHEMA_VERSION,
            "type": generator.resource_type,
            "payload": generator.dump(output),
            "sources": source_refs_for(bundle.units),
            "coverage": coverage_report(bundle, batch_count),
        }
        if regen is not None:  # a preview: nothing the user has is touched (D-92)
            await self._save_preview(content, regen, gsettings)
            return
        source_request = request.source.canonical()
        source_metadata = {
            "source": source_request,
            "documents": [str(d) for d in source.document_ids],
            "model": cfg.internal_id,
            "prompt": f"{generator.prompt_key}:v{prompt_version}",
            **bundle.stats(),
        }
        async with self._factory() as db:
            material = await StudyMaterialRepository(db).create_with_first_version(
                user_id=self.user_id,
                workspace_id=source.workspace_id,
                subject_id=source.subject_id,
                chapter_id=source.chapter_id,
                title=generator.title(output, gsettings)[:300],
                resource_type=generator.resource_type,
                status="completed",
                content=content,
                generation_settings=gsettings.model_dump(mode="json"),
                source_metadata=source_metadata,
            )
            if generator.item_store and generator.key == "quiz":
                await QuizRepository(db).create_quiz(
                    user_id=self.user_id,
                    material_id=material.id,
                    title=material.title,
                    description=getattr(output, "description", "") or None,
                    time_limit=(
                        gsettings.time_limit_minutes * 60  # type: ignore[attr-defined]
                        if gsettings.time_limit_minutes  # type: ignore[attr-defined]
                        else None
                    ),
                    settings=gsettings.model_dump(mode="json"),
                    questions=generated_question_rows(
                        output.questions, source_refs_for(bundle.units)
                    ),
                )
            elif generator.item_store:
                repo = FlashcardRepository(db)
                deck = await repo.create_set(self.user_id, material.id)
                await repo.add_cards(
                    deck, generated_card_rows(output.cards, source_refs_for(bundle.units))
                )
            ok = await GenerationJobRepository(db).finish(
                self.job_id, COMPLETED, _now(), material_id=material.id
            )
            if not ok:  # cancelled or swept at the last moment: keep nothing
                await db.rollback()
                raise _Cancelled
            await db.commit()

    async def _save_preview(
        self, content: dict[str, Any], regen: dict[str, Any], gsettings: GeneratorSettings
    ) -> None:
        preview = {
            "material_id": regen["material_id"],
            "base_version": regen["base_version"],
            "section_index": regen.get("section_index"),
            **{k: regen[k] for k in ("set_id", "card_ids", "revisions") if k in regen},
            "content": content,
            "settings": gsettings.model_dump(mode="json"),
        }
        async with self._factory() as db:
            ok = await GenerationJobRepository(db).finish(
                self.job_id, COMPLETED, _now(), preview=preview
            )
            if not ok:
                await db.rollback()
                raise _Cancelled
            await db.commit()

    async def finish_unsuccessful(self, outcome: str, code: str) -> str:
        """Record failed/cancelled. Returns the job's real final state (first writer wins)."""
        async with self._factory() as db:
            repo = GenerationJobRepository(db)
            changed = await repo.finish(self.job_id, outcome, _now(), error_code=code)
            job = await repo.get(self.job_id)
            if job is not None and job.request.get("source", {}).get("text") is not None:
                job.request = redact_request(job.request)
            await db.commit()
            if changed or job is None:
                return outcome
            return str(job.status)
