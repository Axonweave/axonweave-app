"""Study generation service: validation, ownership, limits, quotas, duplicate prevention.

Order of checks for a new request (CLAUDE.md rule 1): authenticated (route) -> configured ->
generator and settings valid -> every source id belongs to this user (404 otherwise) -> something
is ready to read -> identical active job? return it -> per-minute limit, daily quota, active-job cap
-> create and dispatch. No business logic lives in the route handlers."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.errors import AiQuotaExceededError, LLMNotConfiguredError
from app.ai.orchestration.runtime import AiRuntime
from app.core.rate_limit import RateLimiter
from app.models.generation_job import GenerationJob
from app.models.study_material import StudyMaterial
from app.models.user import User
from app.modules.study.preferences_service import StudyPreferencesService
from app.repositories.ai_usage_repository import AiUsageRepository, utc_day_start
from app.repositories.generation_job_repository import GenerationJobRepository
from app.repositories.study_material_repository import StudyMaterialRepository
from app.study.dispatch import GenerationDispatcher
from app.study.engine import redact_request
from app.study.errors import (
    GenerationNotFoundError,
    GenerationQuotaExceededError,
    GenerationUnavailableError,
    NotCancellableError,
    SourceTooLargeError,
    SourceTooSmallError,
    TooManyActiveGenerationsError,
)
from app.study.generators.registry import available_generators, get_generator, validate_settings
from app.study.schemas import GenerationRequest, fingerprint
from app.study.source_reader import SourceReader

logger = structlog.get_logger(__name__)


def _seconds_until_utc_midnight() -> int:
    now = datetime.now(UTC)
    midnight = (now.replace(hour=0, minute=0, second=0, microsecond=0)).timestamp() + 86400
    return max(1, int(midnight - now.timestamp()))


class StudyGenerationService:
    def __init__(
        self,
        db: AsyncSession,
        runtime: AiRuntime,
        dispatcher: GenerationDispatcher,
        limiter: RateLimiter,
    ) -> None:
        self._db = db
        self._rt = runtime
        self._s = runtime.settings
        self._dispatcher = dispatcher
        self._limiter = limiter
        self._jobs = GenerationJobRepository(db)

    async def create(
        self,
        user: User,
        request: GenerationRequest,
        regenerate: dict[str, object] | None = None,
    ) -> tuple[GenerationJob, bool]:
        """Returns (job, existing); `existing` is True when an identical request is active.
        `regenerate` is set only by `regenerate_material`; clients cannot send it."""
        if not self._rt.registry.configured:
            raise LLMNotConfiguredError()
        if not self._dispatcher.available():
            raise GenerationUnavailableError()

        generator = get_generator(request.generation_type, self._s)
        requested = request.settings
        if regenerate is None:  # a regeneration already carries the material's own settings
            requested = await StudyPreferencesService(self._db).defaults_for(
                user.id, generator, requested
            )
        settings = validate_settings(generator, requested)
        normalised = settings.model_dump(mode="json")

        reader = SourceReader(self._db, self._s)
        source = await reader.resolve(user.id, request.source)  # 404 for a foreign id
        estimate = await reader.estimate(source)  # NoSourcesError when nothing is ready
        if regenerate is None and estimate.tokens < generator.min_source_tokens:
            raise SourceTooSmallError()
        if generator.source_mode == "ordered" and not generator.allow_sampled_fallback:
            limit = (
                self._s.study_max_scope_tokens
                if generator.map_reduce
                else self._s.study_max_input_tokens
            )
            if estimate.tokens > limit:
                raise SourceTooLargeError()

        digest = fingerprint(
            user.id,
            generator.key,
            request.source,
            {"s": normalised, "r": regenerate} if regenerate else normalised,
        )
        existing = await self._jobs.find_active_by_fingerprint(user.id, digest)
        if existing is not None:
            return existing, True

        await self._enforce_limits(user.id)

        body = {
            "generation_type": generator.key,
            "source": request.source.model_dump(mode="json", exclude_none=True),
            "settings": normalised,
        }
        if regenerate:
            body["regenerate"] = regenerate
        try:
            job = await self._jobs.add(
                user_id=user.id,
                generation_type=generator.key,
                status="pending",
                fingerprint=digest,
                request=body,
            )
            await self._db.commit()
        except IntegrityError:  # a concurrent identical request won the unique index
            await self._db.rollback()
            existing = await self._jobs.find_active_by_fingerprint(user.id, digest)
            if existing is None:
                raise
            return existing, True
        if not self._dispatcher.dispatch(job.id):
            logger.warning("generation_left_pending", job_id=str(job.id))
        logger.info("generation_created", job_id=str(job.id), generation_type=generator.key)
        return job, False

    async def _enforce_limits(self, user_id: uuid.UUID) -> None:
        s = self._s
        try:
            await self._limiter.check(
                f"study:user:{user_id}", s.study_requests_per_minute_per_user, 60
            )
        except HTTPException:
            raise GenerationQuotaExceededError(retry_after=60) from None
        reset_in = _seconds_until_utc_midnight()
        if await self._jobs.count_since(user_id, utc_day_start()) >= s.study_daily_generation_quota:
            raise GenerationQuotaExceededError(retry_after=reset_in)
        if await AiUsageRepository(self._db).tokens_today(user_id) >= s.ai_daily_token_quota:
            raise AiQuotaExceededError(retry_after=reset_in)
        if await self._jobs.count_active(user_id) >= s.study_max_active_jobs_per_user:
            raise TooManyActiveGenerationsError

    async def get(self, user: User, job_id: uuid.UUID) -> GenerationJob:
        job = await self._jobs.get_owned(job_id, user.id)
        if job is None:
            raise GenerationNotFoundError
        return job

    async def list(
        self, user: User, *, status: str | None, limit: int, offset: int
    ) -> tuple[list[GenerationJob], int]:
        return await self._jobs.list_for_user(user.id, status=status, limit=limit, offset=offset)

    async def cancel(self, user: User, job_id: uuid.UUID) -> GenerationJob:
        job = await self.get(user, job_id)  # ownership first: a foreign id is a 404
        result = await self._jobs.request_cancel(job_id, user.id, datetime.now(UTC))
        if result == "finished":
            raise NotCancellableError
        if result == "cancelled" and job.request.get("source", {}).get("text") is not None:
            await self._db.refresh(job)
            job.request = redact_request(job.request)
        await self._db.commit()
        await self._db.refresh(job)
        return job

    async def get_material(self, user: User, material_id: uuid.UUID) -> StudyMaterial:
        material = await StudyMaterialRepository(self._db).get_owned(material_id, user.id)
        if material is None:
            raise HTTPException(
                404, detail={"code": "RESOURCE_NOT_FOUND", "message": "Study material not found."}
            )
        return material

    def generators(self) -> list[tuple[str, str, dict[str, object]]]:
        return [
            (g.key, g.resource_type, g.settings_model.model_json_schema())
            for g in available_generators(self._s)
        ]
