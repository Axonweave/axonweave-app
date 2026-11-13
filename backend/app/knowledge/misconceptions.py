"""Misconception detection (Milestone 6.7, spec section 15).

A misconception is a recurring misunderstanding, not a wrong answer. Safeguards, all enforced in
code (the model never decides them):

* Detection only runs when a concept has at least MIN_WRONG_ANSWERS wrong answers on at least
  MIN_QUESTIONS different questions. Blank answers and answers to questions the learner has since
  answered correctly are left out (gaps and slips are not misconceptions).
* The model sees opaque tags (A1.., C1..), never database ids. Whatever it cites is mapped back
  here; a tag it invents is ignored, and a misconception needs at least two cited answers on
  different questions or it is dropped. Confidence under MIN_CONFIDENCE is dropped, never shown as
  fact; the stored value is capped at MAX_CONFIDENCE.
* The same evidence, versions and settings give the same fingerprint, so a repeated request makes no
  new provider call (retry-safe). A dismissed misconception is never recreated.
* Answer text is read from the learner's own quiz data at view time; only ids are stored. Nothing
  here logs prompts, answers or model replies.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
import uuid
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any

import structlog
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.errors import (
    AiQuotaExceededError,
    LLMContentBlockedError,
    LLMError,
    LLMNotConfiguredError,
)
from app.ai.model_registry import ModelConfig
from app.ai.orchestration.runtime import AiRuntime
from app.ai.prompts import knowledge as prompts
from app.ai.prompts.registry import active_prompt
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
from app.core.rate_limit import RateLimiter
from app.knowledge.errors import KnowledgeError, NodeNotFoundError
from app.knowledge.normalise import normalise_name
from app.models.learner import LearnerMisconception
from app.models.llm_provider import LLMModel
from app.models.quiz import QuizAttemptAnswer, QuizQuestion
from app.repositories.ai_catalog_repository import AiCatalogRepository
from app.repositories.ai_usage_repository import AiUsageRepository
from app.repositories.learner_misconception_repository import LearnerMisconceptionRepository
from app.repositories.learner_state_repository import LearnerStateRepository
from app.study.generators.base import OutputInvalid
from app.study.prompting import correction_turn
from app.study.validation import describe_errors, parse_json_object

logger = structlog.get_logger(__name__)

MIN_WRONG_ANSWERS = 3
MIN_QUESTIONS = 2
MAX_ANSWERS_SENT = 8
MAX_NEIGHBOURS = 8
MAX_ITEMS = 3
MIN_CONFIDENCE = 0.5
MAX_CONFIDENCE = 0.95
FIELD_CHARS = 400
MAX_OUTPUT_TOKENS = 1200
STATUS_DISMISSED = "dismissed"


class MisconceptionNotFoundError(KnowledgeError):
    code = "RESOURCE_NOT_FOUND"
    http_status = 404
    user_message = "Misconception not found."


class _Item(BaseModel):
    model_config = ConfigDict(extra="ignore")

    misconception: str = Field(min_length=8, max_length=300)
    explanation: str = Field(min_length=8, max_length=900)
    recommended_action: str | None = Field(default=None, max_length=300)
    confidence: float = Field(ge=0, le=1)
    observed_evidence: list[str] = Field(min_length=1, max_length=MAX_ANSWERS_SENT)
    related_concepts: list[str] = Field(default_factory=list, max_length=MAX_NEIGHBOURS)


class MisconceptionOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    misconceptions: list[_Item] = Field(default_factory=list, max_length=10)


@dataclass(frozen=True)
class Verified:
    description: str
    explanation: str
    recommended_action: str | None
    confidence: float
    answers: list[tuple[uuid.UUID, uuid.UUID]]  # (answer id, question id)
    related: list[uuid.UUID]


@dataclass
class DetectResult:
    outcome: str  # created | existing | none_found | insufficient_evidence
    items: list[LearnerMisconception] = field(default_factory=list)
    wrong_answers: int = 0
    questions: int = 0


def clean_text(text: str, limit: int) -> str:
    return " ".join(text.replace("<", " ").replace(">", " ").split())[:limit]


def _plain(value: Any) -> str:
    if isinstance(value, list):
        return "; ".join(_plain(v) for v in value)
    if isinstance(value, dict):
        return "; ".join(f"{k}: {_plain(v)}" for k, v in value.items())
    return str(value)


def verify(
    out: MisconceptionOutput,
    answer_tags: dict[str, tuple[uuid.UUID, uuid.UUID]],
    concept_tags: dict[str, uuid.UUID],
) -> list[Verified]:
    """Keep only what the evidence supports. Pure: no I/O."""
    kept: list[Verified] = []
    seen: set[str] = set()
    for item in out.misconceptions:
        cited: dict[uuid.UUID, uuid.UUID] = {}
        for tag in item.observed_evidence:
            hit = answer_tags.get(tag.strip().upper())
            if hit is not None:
                cited[hit[0]] = hit[1]
        if len(set(cited.values())) < MIN_QUESTIONS:
            continue  # one question's worth of evidence is not a pattern
        if item.confidence < MIN_CONFIDENCE:
            continue
        description = clean_text(item.misconception, 300)
        key = normalise_name(description)
        if not description or key in seen:
            continue
        seen.add(key)
        related: list[uuid.UUID] = []
        for tag in item.related_concepts:
            node = concept_tags.get(tag.strip().upper())
            if node is not None and node not in related:
                related.append(node)
        action = clean_text(item.recommended_action, 300) if item.recommended_action else None
        kept.append(
            Verified(
                description=description,
                explanation=clean_text(item.explanation, 900),
                recommended_action=action or None,
                confidence=round(min(item.confidence, MAX_CONFIDENCE), 3),
                answers=list(cited.items()),
                related=related,
            )
        )
    return kept[:MAX_ITEMS]


def description_key(description: str) -> str:
    return hashlib.sha256(normalise_name(description).encode("utf-8")).hexdigest()


def fingerprint(
    user_id: uuid.UUID, node_id: uuid.UUID, answer_ids: list[uuid.UUID], versions: str
) -> str:
    body = f"{user_id}|{node_id}|{versions}|" + ",".join(sorted(str(a) for a in answer_ids))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


class MisconceptionService:
    def __init__(self, db: AsyncSession, runtime: AiRuntime, limiter: RateLimiter) -> None:
        self._db = db
        self._rt = runtime
        self._s = runtime.settings
        self._limiter = limiter
        self._repo = LearnerMisconceptionRepository(db)

    async def detect(self, user_id: uuid.UUID, node_id: uuid.UUID) -> DetectResult:
        node = (await LearnerStateRepository(self._db).nodes(user_id, [node_id])).get(node_id)
        if node is None:
            raise NodeNotFoundError()

        wrong = await self._repo.uncorrected_wrong_answers(user_id, node_id, MAX_ANSWERS_SENT)
        questions = len({q.id for _, q in wrong})
        if len(wrong) < MIN_WRONG_ANSWERS or questions < MIN_QUESTIONS:
            return DetectResult("insufficient_evidence", [], len(wrong), questions)

        prompt = active_prompt(prompts.MISCONCEPTION_KEY)
        prompt_version = f"{prompt.prompt_key}:v{prompt.version}"
        versions = f"{self._s.knowledge_misconception_version}|{prompt_version}"
        digest = fingerprint(user_id, node_id, [a.id for a, _ in wrong], versions)
        existing = await self._repo.by_fingerprint(user_id, node_id, digest)
        if existing:
            return DetectResult("existing", existing, len(wrong), questions)

        if not self._rt.registry.configured:
            raise LLMNotConfiguredError()
        await self._enforce_limits(user_id)

        neighbours = await self._repo.neighbours(user_id, node_id, MAX_NEIGHBOURS)
        answer_tags = {f"A{i + 1}": (a.id, q.id) for i, (a, q) in enumerate(wrong)}
        concept_tags = {f"C{i + 1}": n.id for i, n in enumerate(neighbours)}
        turn = self._build_turn(node.name, wrong, neighbours)

        cfg, catalog = await self._select_model()
        output = await self._call_validated(
            user_id, cfg, catalog, prompt.content, turn, answer_tags, concept_tags
        )
        if output is None:
            return DetectResult("none_found", [], len(wrong), questions)

        created = await self._persist(
            user_id, node.workspace_id, node_id, output, digest, prompt_version, cfg
        )
        await self._db.commit()
        outcome = "created" if created else "none_found"
        return DetectResult(outcome, created, len(wrong), questions)

    # prompt ──────────────────────────────────────────────────────────────────

    def _build_turn(
        self,
        name: str,
        wrong: list[tuple[QuizAttemptAnswer, QuizQuestion]],
        neighbours: list[Any],
    ) -> str:
        parts = [f"CONCEPT: {clean_text(name, 200)}", ""]
        for i, (ans, q) in enumerate(wrong):
            parts.append(
                f"<<<ANSWER A{i + 1}>>>\n"
                f"Question: {clean_text(q.question, FIELD_CHARS)}\n"
                f"Expected answer: {clean_text(_plain(q.correct_answers), FIELD_CHARS)}\n"
                f"Student's answer: {clean_text(_plain(ans.submitted_answer), FIELD_CHARS)}\n"
                "<<<END ANSWER>>>"
            )
        if neighbours:
            parts += ["", "RELATED CONCEPTS:"]
            parts += [f"C{i + 1}: {clean_text(n.name, 120)}" for i, n in enumerate(neighbours)]
        schema = (
            '{"misconceptions": [{"misconception": str, "explanation": str, '
            '"recommended_action": str, "confidence": 0..1, "observed_evidence": ["A1", ...], '
            '"related_concepts": ["C1", ...]}]}'
        )
        parts += [
            "",
            f"TASK: Return at most {MAX_ITEMS} items as JSON: {schema}. Return "
            '{"misconceptions": []} if there is no clear recurring misunderstanding.',
        ]
        return "\n".join(parts)

    # provider ────────────────────────────────────────────────────────────────

    async def _enforce_limits(self, user_id: uuid.UUID) -> None:
        from fastapi import HTTPException

        from app.knowledge.errors import ExtractionRateLimitedError

        try:
            await self._limiter.check(
                f"misconception:user:{user_id}", self._s.knowledge_requests_per_minute_per_user, 60
            )
        except HTTPException:
            raise ExtractionRateLimitedError(retry_after=60) from None
        if await AiUsageRepository(self._db).tokens_today(user_id) >= self._s.ai_daily_token_quota:
            now = datetime.now(UTC)
            midnight = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() + 86400
            raise AiQuotaExceededError(retry_after=max(1, int(midnight - now.timestamp())))

    async def _select_model(self) -> tuple[ModelConfig, LLMModel]:
        cfg = self._rt.registry.resolve(self._s.knowledge_misconception_model or None)
        row = await AiCatalogRepository(self._db).get_model(cfg.internal_id)
        if row is None:
            raise LLMNotConfiguredError()
        return cfg, row

    def _request(
        self, cfg: ModelConfig, system_prompt: str, messages: list[LLMMessage]
    ) -> LLMRequest:
        s = self._s
        return LLMRequest(
            model=cfg.provider_model_id,
            messages=messages,
            max_output_tokens=min(MAX_OUTPUT_TOKENS, cfg.max_output_tokens or 10**9),
            system_prompt=system_prompt,
            temperature=cfg.default_temperature,
            timeouts=TimeoutPolicy(
                connect=s.llm_connect_timeout_seconds,
                generation=s.llm_generation_timeout_seconds,
                stream_inactivity=s.llm_stream_inactivity_timeout_seconds,
                overall=s.llm_overall_timeout_seconds,
            ),
            thinking_budget=s.llm_thinking_budget if cfg.capabilities.thinking_budget else None,
            request_tag="misconception",
        )

    async def _call_validated(
        self,
        user_id: uuid.UUID,
        cfg: ModelConfig,
        catalog: LLMModel,
        system_prompt: str,
        turn: str,
        answer_tags: dict[str, tuple[uuid.UUID, uuid.UUID]],
        concept_tags: dict[str, uuid.UUID],
    ) -> list[Verified] | None:
        """One provider call and at most ONE correction call for malformed output. Returns the
        verified items, or None when the model reported nothing that survives verification."""
        schema = MisconceptionOutput.model_json_schema()
        request = self._request(cfg, system_prompt, [LLMMessage(Role.user, turn)])

        def parse(raw: str) -> list[Verified]:
            try:
                data = parse_json_object(raw)
                return verify(MisconceptionOutput.model_validate(data), answer_tags, concept_tags)
            except ValidationError as exc:
                raise OutputInvalid(describe_errors(exc)) from None

        response = await self._call(user_id, cfg, catalog, request, schema)
        try:
            kept = parse(response.content)
        except OutputInvalid as bad:
            retry = replace(
                request,
                messages=[
                    *request.messages,
                    LLMMessage(Role.assistant, response.content[: MAX_OUTPUT_TOKENS * 4]),
                    LLMMessage(Role.user, correction_turn(str(bad))),
                ],
            )
            response = await self._call(user_id, cfg, catalog, retry, schema)
            try:
                kept = parse(response.content)
            except OutputInvalid:
                logger.info("misconception_output_invalid")
                return None
        return kept or None

    async def _call(
        self,
        user_id: uuid.UUID,
        cfg: ModelConfig,
        catalog: LLMModel,
        request: LLMRequest,
        schema: dict[str, Any],
    ) -> LLMResponse:
        provider = self._rt.provider()
        started = time.monotonic()
        try:
            async with asyncio.timeout(self._s.llm_overall_timeout_seconds + 5):
                if cfg.capabilities.structured_output:
                    response = await provider.generate_structured(request, schema)
                else:
                    response = await provider.generate(request)
        except (LLMError, TimeoutError) as exc:
            code = exc.code if isinstance(exc, LLMError) else "LLM_TIMEOUT"
            await self._usage(user_id, cfg, catalog, Usage(), "failed", code, started, None)
            await self._db.commit()
            raise
        if response.finish_reason is FinishReason.content_filter:
            await self._usage(
                user_id,
                cfg,
                catalog,
                response.usage,
                "failed",
                LLMContentBlockedError.code,
                started,
                response,
            )
            await self._db.commit()
            raise LLMContentBlockedError
        await self._usage(user_id, cfg, catalog, response.usage, "success", None, started, response)
        await self._db.commit()
        return response

    async def _usage(
        self,
        user_id: uuid.UUID,
        cfg: ModelConfig,
        catalog: LLMModel,
        usage: Usage,
        status: str,
        error_code: str | None,
        started: float,
        response: LLMResponse | None,
    ) -> None:
        """One `ai_usage_records` row per provider attempt; counts toward the daily quota."""
        price = find_price(cfg.provider, cfg.provider_model_id)
        cost = estimate_cost(price, usage)
        await AiUsageRepository(self._db).add(
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
            request_kind="misconception",
            request_status=status,
            error_code=error_code,
            duration_ms=int((time.monotonic() - started) * 1000),
            provider_request_id=response.provider_request_id if response else None,
        )

    # persistence ─────────────────────────────────────────────────────────────

    async def _persist(
        self,
        user_id: uuid.UUID,
        workspace_id: uuid.UUID,
        node_id: uuid.UUID,
        items: list[Verified],
        digest: str,
        prompt_version: str,
        cfg: ModelConfig,
    ) -> list[LearnerMisconception]:
        created: list[LearnerMisconception] = []
        for item in items:
            mid = await self._repo.insert(
                {
                    "user_id": user_id,
                    "workspace_id": workspace_id,
                    "knowledge_node_id": node_id,
                    "description": item.description,
                    "explanation": item.explanation,
                    "recommended_action": item.recommended_action,
                    "confidence": item.confidence,
                    "status": "suggested",
                    "evidence_count": len(item.answers),
                    "detection_version": self._s.knowledge_misconception_version,
                    "prompt_version": prompt_version,
                    "model_id": cfg.provider_model_id,
                    "fingerprint": digest,
                    "description_key": description_key(item.description),
                    "related_node_ids": [str(n) for n in item.related],
                }
            )
            if mid is None:
                continue  # already known (maybe dismissed): keep the user's decision
            await self._repo.add_evidence(user_id, mid, item.answers)
            row = await self._repo.get(user_id, mid)
            if row is not None:
                created.append(row)
        return created
