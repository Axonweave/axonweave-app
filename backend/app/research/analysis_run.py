"""The paper analysis run (Phase 7 M7.3, spec 25): one paper's file -> structured, evidence-backed
sections -> verification -> persistence, executed in the Celery worker only (rule 13).

It reuses the Phase 6 extraction engine (`_Run`): atomic claim, stage updates, cancellation polling
while the provider call is in flight, bounded retries, ONE correction call for malformed output and
one usage row per provider attempt (`request_kind = 'paper_analysis'`, counted toward the daily
quota). Claims whose quotations cannot be found in the cited passages are dropped. A re-analysis is
a new versioned run: earlier results, evidence and researcher notes are never touched. Nothing here
logs paper text, prompts or model replies.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import structlog
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.ai.errors import AiError
from app.ai.prompts.registry import active_prompt
from app.ai.prompts.research import ANALYSIS_KEY
from app.knowledge.extraction import (
    CANCELLED,
    COMPLETED,
    FAILED,
    SKIPPED,
    ExtractionDeps,
    _Cancelled,
    _InvalidOutput,
    _NothingVerified,
    _now,
    _Run,
)
from app.models.research import ResearchEvidence
from app.repositories.research_analysis_repository import ResearchAnalysisRepository
from app.research import errors
from app.research.analysis import (
    TASK_BLOCK,
    AnalysisOutput,
    VerifiedAnalysis,
    merge_analyses,
    parse_analysis,
    verify_analysis,
)
from app.study.errors import NoSourcesError, SourceTooLargeError, StudyError
from app.study.prompting import build_user_turn
from app.study.source_reader import SourceBundle

logger = structlog.get_logger(__name__)


async def run_paper_analysis(
    deps: ExtractionDeps, extraction_id: Any, celery_task_id: str | None = None
) -> str:
    """Run one analysis. Returns completed, failed, cancelled or skipped. Failures are recorded on
    the analysis and never raised; only infrastructure errors propagate."""
    async with deps.session_factory() as db:
        repo = ResearchAnalysisRepository(db)
        claimed = await repo.claim(extraction_id, _now(), celery_task_id)
        job = await repo.get(extraction_id) if claimed else None
        paper_id = getattr(job, "research_paper_id", None)
        if paper_id is not None:
            await repo.refresh_paper_status(paper_id)
        await db.commit()
    if job is None:
        logger.info("paper_analysis_skipped", extraction_id=str(extraction_id))
        return SKIPPED

    run = PaperAnalysisRun(deps, job.id, job.user_id, job.document_id, paper_id)
    started = time.monotonic()
    outcome, code = FAILED, errors.INTERNAL
    try:
        if job.document_id is None:
            raise NoSourcesError
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
    except SourceTooLargeError:
        outcome, code = FAILED, errors.TOO_LARGE
    except NoSourcesError:
        outcome, code = FAILED, errors.SOURCES_GONE
    except (StudyError, AiError) as exc:
        outcome, code = FAILED, exc.code
    except (HTTPException, IntegrityError):  # file or paper removed mid-run
        outcome, code = FAILED, errors.SOURCES_GONE
    except Exception as exc:  # never leak details: type name only
        if type(exc).__name__ == "SoftTimeLimitExceeded":
            outcome, code = FAILED, errors.TIMEOUT
        else:
            logger.error(
                "paper_analysis_unexpected_error",
                extraction_id=str(extraction_id),
                error_type=type(exc).__name__,
            )
    if outcome != COMPLETED:
        outcome = await run.finish_unsuccessful(outcome, code)
    logger.info(
        "paper_analysis_finished",
        extraction_id=str(extraction_id),
        outcome=outcome,
        error_code=code or None,
        duration_ms=int((time.monotonic() - started) * 1000),
    )
    return outcome


class PaperAnalysisRun(_Run):
    request_kind = "paper_analysis"
    task_block = TASK_BLOCK

    def __init__(
        self, deps: ExtractionDeps, job_id: Any, user_id: Any, document_id: Any, paper_id: Any
    ) -> None:
        super().__init__(deps, job_id, user_id, document_id)
        self.paper_id = paper_id

    def _jobs(self, db: Any) -> Any:
        return ResearchAnalysisRepository(db)

    def _configured_model(self) -> str:
        return self._s.research_analysis_model

    async def execute(self) -> None:
        prompt = active_prompt(ANALYSIS_KEY)
        cfg, catalog = await self._select_model()
        await self._stage(
            "retrieving_sources",
            10,
            model_identifier=cfg.internal_id,
            prompt_version=f"{prompt.prompt_key}:v{prompt.version}",
        )
        budget = self._input_budget(cfg, prompt.content)
        placement, batches = await self._read_sources(budget)
        await self._checkpoint()

        parts: list[VerifiedAnalysis] = []
        for i, bundle in enumerate(batches):
            await self._stage("extracting", 15 + int(60 * i / len(batches)))
            parts.append(await self._analyse_batch(cfg, catalog, prompt.content, bundle))
            await self._checkpoint()

        await self._stage("validating", 80)
        result = merge_analyses(parts)
        if result.claim_count == 0:
            raise _NothingVerified
        await self._checkpoint()
        await self._stage("saving", 90)
        await self._save_analysis(placement.document_version_id, result, len(batches))

    async def _analyse_batch(
        self, cfg: Any, catalog: Any, system_prompt: str, bundle: SourceBundle
    ) -> VerifiedAnalysis:
        request = self._llm_request(cfg, system_prompt, build_user_turn(bundle.units, TASK_BLOCK))
        schema = AnalysisOutput.model_json_schema()

        def validate(raw: str) -> VerifiedAnalysis:
            return verify_analysis(parse_analysis(raw), bundle.units)

        result: VerifiedAnalysis = await self._validated_call(
            cfg, catalog, request, schema, validate
        )
        return result

    async def _save_analysis(self, version_id: Any, result: VerifiedAnalysis, batches: int) -> None:
        """Store claims, evidence and the completed state in ONE transaction: a failed save leaves
        nothing half-written and the run is never marked completed."""
        async with self._factory() as db:
            repo = ResearchAnalysisRepository(db)
            project_id = await repo.paper_project_id(self.paper_id)
            if project_id is None:  # the paper was removed while we worked
                raise _Cancelled
            evidence: list[ResearchEvidence] = []
            structured: dict[str, list[dict[str, Any]]] = {}
            for section, claims in result.sections.items():
                structured[section] = []
                for index, claim in enumerate(claims):
                    structured[section].append(
                        {
                            "index": index,
                            "label": claim.label,
                            "text": claim.text,
                            "origin": claim.origin,
                            "confidence": claim.confidence,
                        }
                    )
                    evidence.extend(
                        ResearchEvidence(
                            user_id=self.user_id,
                            research_project_id=project_id,
                            research_paper_id=self.paper_id,
                            extraction_id=self.job_id,
                            claim_type=section,
                            claim_index=index,
                            label=claim.label,
                            claim_text=claim.text,
                            document_id=ev.unit.document_id,
                            document_version_id=version_id,
                            chunk_id=ev.unit.chunk_id,
                            page_number=ev.unit.page_number,
                            supporting_text=ev.quote,
                            confidence=claim.confidence,
                            evidence_origin=claim.origin,
                        )
                        for ev in claim.evidence
                    )
            stats = {
                "claims": result.claim_count,
                "evidence": len(evidence),
                "dropped": result.dropped,
                "batches": batches,
                "per_section": {name: len(items) for name, items in result.sections.items()},
            }
            done = await repo.finish(
                self.job_id,
                COMPLETED,
                _now(),
                result_stats=stats,
                structured_result={"sections": structured},
            )
            if not done:  # cancelled or failed by the sweeper while we worked: save nothing
                await db.rollback()
                raise _Cancelled
            await repo.add_evidence(evidence)
            await repo.refresh_paper_status(self.paper_id)
            await db.commit()

    async def finish_unsuccessful(self, outcome: str, code: str) -> str:
        final = await super().finish_unsuccessful(outcome, code)
        async with self._factory() as db:
            await ResearchAnalysisRepository(db).refresh_paper_status(self.paper_id)
            await db.commit()
        return final
