"""Paper analysis and notes service (Phase 7 M7.3).

Order of checks (CLAUDE.md rule 1): authenticated (route) -> AI configured -> the paper is this
user's (404 otherwise, parents included) -> not archived -> has a processed file -> an active
analysis? return it -> per-minute limit, daily token quota, active cap -> create and dispatch.
No business logic in the route handlers.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, datetime

import structlog
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.errors import AiQuotaExceededError, LLMNotConfiguredError
from app.ai.orchestration.runtime import AiRuntime
from app.ai.prompts.research import ANALYSIS_VERSION
from app.core.rate_limit import RateLimiter
from app.knowledge.dispatch import ExtractionDispatcher
from app.models.research import SECTIONS, ResearchPaper, ResearchPaperExtraction, ResearchPaperNote
from app.models.user import User
from app.modules.research.analysis_schemas import (
    PaperAnalysisOut,
    PaperAnalysisRunOut,
    PaperClaimOut,
    PaperEvidenceOut,
    PaperNoteCreate,
    PaperSectionOut,
)
from app.repositories.ai_usage_repository import AiUsageRepository
from app.repositories.research_analysis_repository import ResearchAnalysisRepository
from app.repositories.research_paper_repository import ResearchPaperRepository
from app.repositories.research_project_repository import ResearchProjectRepository
from app.research.errors import (
    AnalysisNotCancellableError,
    AnalysisNotFoundError,
    AnalysisRateLimitedError,
    AnalysisUnavailableError,
    NoteNotFoundError,
    PaperArchivedError,
    PaperFileNotReadyError,
    PaperHasNoFileError,
    PaperNotFoundError,
    ProjectArchivedError,
    ProjectNotFoundError,
    TooManyActiveAnalysesError,
    safe_analysis_message,
)
from app.study.errors import NoSourcesError
from app.study.schemas import SourceSpec
from app.study.source_reader import SourceReader

logger = structlog.get_logger(__name__)


def _seconds_until_utc_midnight() -> int:
    now = datetime.now(UTC)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() + 86400
    return max(1, int(midnight - now.timestamp()))


def run_out(run: ResearchPaperExtraction, *, existing: bool = False) -> PaperAnalysisRunOut:
    out = PaperAnalysisRunOut.model_validate(run)
    out.error_message = safe_analysis_message(run.error_code)
    out.existing = existing
    return out


class PaperAnalysisService:
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
        self._repo = ResearchAnalysisRepository(db)

    async def _paper(self, user: User, paper_id: uuid.UUID) -> ResearchPaper:
        row = await ResearchPaperRepository(self._db).get(user.id, paper_id)
        if row is None:
            raise PaperNotFoundError()
        return row[0]

    # start / cancel ──────────────────────────────────────────────────────────

    async def start(self, user: User, paper_id: uuid.UUID) -> tuple[ResearchPaperExtraction, bool]:
        """Returns (analysis, existing); `existing` is True when one is already running."""
        if not self._rt.registry.configured:
            raise LLMNotConfiguredError()
        if not self._dispatcher.available():
            raise AnalysisUnavailableError()
        paper = await self._paper(user, paper_id)
        project = await ResearchProjectRepository(self._db).get(user.id, paper.research_project_id)
        if project is None:
            raise ProjectNotFoundError()
        if project.archived_at is not None:
            raise ProjectArchivedError()
        if paper.archived_at is not None:
            raise PaperArchivedError()
        if paper.document_id is None:
            raise PaperHasNoFileError()
        try:  # 404 for a foreign or missing file; NoSourcesError when it is not ready yet
            reader = SourceReader(self._db, self._s)
            source = await reader.resolve(
                user.id, SourceSpec(type="document", id=paper.document_id)
            )
            await reader.estimate(source)
        except NoSourcesError:
            raise PaperFileNotReadyError() from None

        active = await self._repo.active_for_paper(user.id, paper.id)
        if active is not None:
            return active, True
        await self._enforce_limits(user.id)

        try:
            run = ResearchPaperExtraction(
                user_id=user.id,
                research_paper_id=paper.id,
                version_number=await self._repo.next_version(paper.id),
                status="pending",
                progress=0,
                extraction_version=self._s.research_analysis_version,
                prompt_version=f"research_paper_analysis:v{ANALYSIS_VERSION}",
                document_id=paper.document_id,
                cancel_requested=False,
                provider_calls=0,
            )
            self._db.add(run)
            await self._db.flush()
            await self._repo.refresh_paper_status(paper.id)
            await self._db.commit()
        except IntegrityError:  # a concurrent request won the one-active-run index
            await self._db.rollback()
            active = await self._repo.active_for_paper(user.id, paper.id)
            if active is None:
                raise
            return active, True
        if not self._dispatcher.dispatch(run.id):
            logger.warning("paper_analysis_left_pending", extraction_id=str(run.id))
        logger.info("paper_analysis_created", extraction_id=str(run.id))
        return run, False

    async def _enforce_limits(self, user_id: uuid.UUID) -> None:
        s = self._s
        try:
            await self._limiter.check(
                f"research-analysis:user:{user_id}",
                s.research_analysis_requests_per_minute_per_user,
                60,
            )
        except HTTPException:
            raise AnalysisRateLimitedError(retry_after=60) from None
        if await AiUsageRepository(self._db).tokens_today(user_id) >= s.ai_daily_token_quota:
            raise AiQuotaExceededError(retry_after=_seconds_until_utc_midnight())
        if await self._repo.count_active(user_id) >= s.research_max_active_analyses_per_user:
            raise TooManyActiveAnalysesError()

    async def cancel(
        self, user: User, paper_id: uuid.UUID, extraction_id: uuid.UUID
    ) -> ResearchPaperExtraction:
        run = await self._run(user, paper_id, extraction_id)  # ownership first: foreign = 404
        result = await self._repo.request_cancel(run.id, user.id, datetime.now(UTC))
        if result == "finished":
            raise AnalysisNotCancellableError()
        await self._repo.refresh_paper_status(paper_id)
        await self._db.commit()
        await self._db.refresh(run)
        return run

    # reads ───────────────────────────────────────────────────────────────────

    async def _run(
        self, user: User, paper_id: uuid.UUID, extraction_id: uuid.UUID
    ) -> ResearchPaperExtraction:
        await self._paper(user, paper_id)
        run = await self._repo.get_for_paper(user.id, paper_id, extraction_id)
        if run is None:
            raise AnalysisNotFoundError()
        return run

    async def get_run(
        self, user: User, paper_id: uuid.UUID, extraction_id: uuid.UUID
    ) -> ResearchPaperExtraction:
        return await self._run(user, paper_id, extraction_id)

    async def history(
        self, user: User, paper_id: uuid.UUID, *, limit: int, offset: int
    ) -> tuple[list[ResearchPaperExtraction], int]:
        await self._paper(user, paper_id)
        return await self._repo.list_for_paper(user.id, paper_id, limit=limit, offset=offset)

    async def analysis(
        self, user: User, paper_id: uuid.UUID, version: int | None
    ) -> PaperAnalysisOut:
        """Every section of one completed run (the latest unless `version` is given). Sections the
        run found nothing for are present with no items."""
        await self._paper(user, paper_id)
        active = await self._repo.active_for_paper(user.id, paper_id)
        run: ResearchPaperExtraction | None
        if version is None:
            run = await self._repo.latest_completed(user.id, paper_id)
        else:
            run = await self._repo.completed_version(user.id, paper_id, version)
            if run is None:
                raise AnalysisNotFoundError()
        grouped: dict[str, dict[int, PaperClaimOut]] = defaultdict(dict)
        if run is not None:
            claims = (run.structured_result or {}).get("sections", {})
            for section in SECTIONS:
                for item in claims.get(section, []):
                    grouped[section][item["index"]] = PaperClaimOut(
                        index=item["index"],
                        label=item.get("label"),
                        text=item["text"],
                        origin=item["origin"],
                        confidence=item.get("confidence"),
                        evidence=[],
                    )
            for ev in await self._repo.evidence_for(user.id, run.id):
                claim = grouped[ev.claim_type].get(ev.claim_index)
                if claim is not None:
                    claim.evidence.append(
                        PaperEvidenceOut(
                            id=ev.id,
                            document_id=ev.document_id,
                            chunk_id=ev.chunk_id,
                            page_number=ev.page_number,
                            quote=ev.supporting_text,
                        )
                    )
        return PaperAnalysisOut(
            run=run_out(run) if run is not None else None,
            active=run_out(active) if active is not None else None,
            sections=[
                PaperSectionOut(
                    section=name,  # type: ignore[arg-type]
                    items=[grouped[name][i] for i in sorted(grouped[name])],
                )
                for name in SECTIONS
            ],
        )

    # notes ───────────────────────────────────────────────────────────────────

    async def list_notes(self, user: User, paper_id: uuid.UUID) -> list[ResearchPaperNote]:
        await self._paper(user, paper_id)
        return await self._repo.list_notes(user.id, paper_id)

    async def add_note(
        self, user: User, paper_id: uuid.UUID, body: PaperNoteCreate
    ) -> ResearchPaperNote:
        await self._paper(user, paper_id)
        note = await self._repo.add_note(
            ResearchPaperNote(
                user_id=user.id,
                research_paper_id=paper_id,
                section=body.section,
                body=body.body,
            )
        )
        await self._db.commit()
        await self._db.refresh(note)
        return note

    async def edit_note(self, user: User, note_id: uuid.UUID, body: str) -> ResearchPaperNote:
        note = await self._repo.get_note(user.id, note_id)
        if note is None:
            raise NoteNotFoundError()
        note.body = body
        await self._db.commit()
        await self._db.refresh(note)
        return note

    async def delete_note(self, user: User, note_id: uuid.UUID) -> None:
        if await self._repo.get_note(user.id, note_id) is None:
            raise NoteNotFoundError()
        await self._repo.delete_note(user.id, note_id)
        await self._db.commit()
