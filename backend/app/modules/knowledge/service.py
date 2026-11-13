"""Knowledge extraction service: ownership, limits, quotas, duplicate prevention.

Order of checks (CLAUDE.md rule 1): authenticated (route) -> configured -> the document is this
user's (404 otherwise) and ready -> identical active job? return it -> per-minute limit, daily
token quota, active-job cap -> create and dispatch. No business logic in the route handlers."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

import structlog
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.errors import AiQuotaExceededError, LLMNotConfiguredError
from app.ai.orchestration.runtime import AiRuntime
from app.ai.prompts import knowledge as prompts
from app.core.rate_limit import RateLimiter
from app.knowledge.dispatch import ExtractionDispatcher
from app.knowledge.errors import (
    DocumentNotReadyError,
    ExtractionJobNotFoundError,
    ExtractionNotCancellableError,
    ExtractionRateLimitedError,
    ExtractionUnavailableError,
    TooManyActiveExtractionsError,
)
from app.models.knowledge import KnowledgeExtractionJob
from app.models.user import User
from app.repositories.ai_usage_repository import AiUsageRepository
from app.repositories.knowledge_job_repository import KnowledgeJobRepository
from app.retrieval.scope import ScopeResolver
from app.study.errors import NoSourcesError
from app.study.schemas import SourceSpec
from app.study.source_reader import SourceReader

logger = structlog.get_logger(__name__)


def _seconds_until_utc_midnight() -> int:
    now = datetime.now(UTC)
    midnight = (now.replace(hour=0, minute=0, second=0, microsecond=0)).timestamp() + 86400
    return max(1, int(midnight - now.timestamp()))


def web_fingerprint(user_id: uuid.UUID, subject_id: uuid.UUID, extraction_version: str) -> str:
    """One active web run per subject: a second request while one is active returns it."""
    payload = {
        "u": str(user_id),
        "kind": "web",
        "s": str(subject_id),
        "v": extraction_version,
        "p": prompts.EXTRACT_VERSION,
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def fingerprint(user_id: uuid.UUID, document_id: uuid.UUID, extraction_version: str) -> str:
    """Identical requests by one user share a fingerprint, so a second identical request while one
    is active returns the active job instead of paying for another extraction."""
    payload = {
        "u": str(user_id),
        "d": str(document_id),
        "v": extraction_version,
        "p": prompts.EXTRACT_VERSION,
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass
class SubjectRunResult:
    """What a whole-subject run did. `ready` counts completed, active documents of the subject."""

    ready: int
    skipped: int = 0  # already extracted at this version
    queued: int = 0
    already_running: int = 0
    not_ready: int = 0
    over_cap: int = 0  # left for the next run
    job_ids: list[uuid.UUID] = field(default_factory=list)


class KnowledgeExtractionService:
    def __init__(
        self,
        db: AsyncSession,
        runtime: AiRuntime,
        dispatcher: ExtractionDispatcher,
        limiter: RateLimiter,
    ) -> None:
        self._db = db
        self._rt = runtime
        self._s = runtime.settings
        self._dispatcher = dispatcher
        self._limiter = limiter
        self._jobs = KnowledgeJobRepository(db)

    async def create(
        self, user: User, document_id: uuid.UUID
    ) -> tuple[KnowledgeExtractionJob, bool]:
        """Returns (job, existing); `existing` is True when an identical request is active."""
        self._require_available()
        return await self._create_one(user, document_id, enforce_limits=True)

    def _require_available(self) -> None:
        if not self._rt.registry.configured:
            raise LLMNotConfiguredError()
        if not self._dispatcher.available():
            raise ExtractionUnavailableError()

    async def create_for_subject(self, user: User, subject_id: uuid.UUID) -> SubjectRunResult:
        """Queue an extraction for every ready document of one subject that has none yet.

        Ownership comes from `ScopeResolver` (a foreign subject is a 404 and queues nothing). The
        per-document limits (6 a minute, 2 active) would reject a loop, so a batch checks the daily
        token quota once and is capped at `knowledge_max_documents_per_subject_run` documents.
        The worker's own concurrency then works through the pending jobs."""
        self._require_available()
        scope = await ScopeResolver(self._db).resolve(user.id, "subject", subject_id)
        ready = list(scope.document_ids)
        version = self._s.knowledge_extraction_version
        done = await self._jobs.completed_document_ids(user.id, ready, version)
        todo = [d for d in ready if d not in done]
        result = SubjectRunResult(ready=len(ready), skipped=len(ready) - len(todo))
        if not todo:
            return result

        # No per-click cooldown: a repeat click while jobs are active just returns them (the
        # fingerprint dedupe), and the daily token quota is the real cost guard.
        if await AiUsageRepository(self._db).tokens_today(user.id) >= self._s.ai_daily_token_quota:
            raise AiQuotaExceededError(retry_after=_seconds_until_utc_midnight())

        cap = self._s.knowledge_max_documents_per_subject_run
        result.over_cap = max(0, len(todo) - cap)
        for document_id in todo[:cap]:
            try:
                job, existing = await self._create_one(user, document_id, enforce_limits=False)
            except DocumentNotReadyError:
                result.not_ready += 1
                continue
            result.job_ids.append(job.id)
            if existing:
                result.already_running += 1
            else:
                result.queued += 1
        return result

    async def create_web(
        self, user: User, subject_id: uuid.UUID
    ) -> tuple[KnowledgeExtractionJob, bool]:
        """Queue a web-grounded run for one subject (D-144). Order: configured, broker, ownership
        (a foreign subject is a 404), an active run is returned, then the daily token quota."""
        self._require_available()
        subject = await self._jobs.owned_subject(user.id, subject_id)
        if subject is None:
            raise ExtractionJobNotFoundError()
        workspace_id, name = subject
        version = self._s.knowledge_extraction_version
        digest = web_fingerprint(user.id, subject_id, version)
        existing = await self._jobs.find_active_by_fingerprint(user.id, digest)
        if existing is not None:
            return existing, True
        if await AiUsageRepository(self._db).tokens_today(user.id) >= self._s.ai_daily_token_quota:
            raise AiQuotaExceededError(retry_after=_seconds_until_utc_midnight())
        try:
            job = await self._jobs.add(
                user_id=user.id,
                workspace_id=workspace_id,
                document_id=None,
                source_kind="web",
                subject_id=subject_id,
                topic=name[:200],
                status="pending",
                extraction_version=version,
                fingerprint=digest,
            )
            await self._db.commit()
        except IntegrityError:  # a concurrent identical request won the unique index
            await self._db.rollback()
            existing = await self._jobs.find_active_by_fingerprint(user.id, digest)
            if existing is None:
                raise
            return existing, True
        if not self._dispatcher.dispatch(job.id):
            logger.warning("extraction_left_pending", job_id=str(job.id))
        logger.info("web_extraction_created", job_id=str(job.id))
        return job, False

    async def _create_one(
        self, user: User, document_id: uuid.UUID, *, enforce_limits: bool
    ) -> tuple[KnowledgeExtractionJob, bool]:
        reader = SourceReader(self._db, self._s)
        try:  # 404 for a foreign or missing document; NoSourcesError when it is not ready yet
            source = await reader.resolve(user.id, SourceSpec(type="document", id=document_id))
            await reader.estimate(source)
        except NoSourcesError:
            raise DocumentNotReadyError() from None

        version = self._s.knowledge_extraction_version
        digest = fingerprint(user.id, document_id, version)
        existing = await self._jobs.find_active_by_fingerprint(user.id, digest)
        if existing is not None:
            return existing, True

        if enforce_limits:
            await self._enforce_limits(user.id)

        try:
            job = await self._jobs.add(
                user_id=user.id,
                workspace_id=source.workspace_id,
                document_id=document_id,
                status="pending",
                extraction_version=version,
                fingerprint=digest,
            )
            await self._db.commit()
        except IntegrityError:  # a concurrent identical request won the unique index
            await self._db.rollback()
            existing = await self._jobs.find_active_by_fingerprint(user.id, digest)
            if existing is None:
                raise
            return existing, True
        if not self._dispatcher.dispatch(job.id):
            logger.warning("extraction_left_pending", job_id=str(job.id))
        logger.info("extraction_created", job_id=str(job.id))
        return job, False

    async def _enforce_limits(self, user_id: uuid.UUID) -> None:
        s = self._s
        try:
            await self._limiter.check(
                f"knowledge:user:{user_id}", s.knowledge_requests_per_minute_per_user, 60
            )
        except HTTPException:
            raise ExtractionRateLimitedError(retry_after=60) from None
        # Extraction counts toward the existing daily token quota (D-124).
        if await AiUsageRepository(self._db).tokens_today(user_id) >= s.ai_daily_token_quota:
            raise AiQuotaExceededError(retry_after=_seconds_until_utc_midnight())
        if await self._jobs.count_active(user_id) >= s.knowledge_max_active_jobs_per_user:
            raise TooManyActiveExtractionsError()

    async def get(self, user: User, job_id: uuid.UUID) -> KnowledgeExtractionJob:
        job = await self._jobs.get_owned(job_id, user.id)
        if job is None:
            raise ExtractionJobNotFoundError()
        return job

    async def list(
        self,
        user: User,
        *,
        status: str | None,
        document_id: uuid.UUID | None,
        limit: int,
        offset: int,
        subject_id: uuid.UUID | None = None,
    ) -> tuple[list[KnowledgeExtractionJob], int]:
        return await self._jobs.list_for_user(
            user.id,
            status=status,
            document_id=document_id,
            limit=limit,
            offset=offset,
            subject_id=subject_id,
        )

    async def cancel(self, user: User, job_id: uuid.UUID) -> KnowledgeExtractionJob:
        job = await self.get(user, job_id)  # ownership first: a foreign id is a 404
        result = await self._jobs.request_cancel(job_id, user.id, datetime.now(UTC))
        if result == "finished":
            raise ExtractionNotCancellableError()
        await self._db.commit()
        await self._db.refresh(job)
        return job
