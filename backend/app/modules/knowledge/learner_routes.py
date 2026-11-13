"""Learner evidence routes (Milestone 6.5). Everything is scoped to the signed-in user; a link id
that is not theirs is a 404. Writes are covered by the app's CSRF protection (D-04)."""

import uuid
from typing import Literal

import structlog
from fastapi import APIRouter, Query

from app.core.dependencies import ActiveUser, DbSession
from app.knowledge.dispatch import RECALC_TASK
from app.knowledge.errors import NodeNotFoundError
from app.knowledge.learner_evidence import LearnerEvidenceService
from app.knowledge.mastery import CALCULATION_VERSION
from app.knowledge.mastery_service import MasteryService
from app.models.learner import KnowledgeConceptLink, LearnerConceptState
from app.modules.knowledge.learner_schemas import (
    ConceptLinkListResponse,
    ConceptLinkOut,
    ConceptLinkResponse,
    ConceptStateListResponse,
    ConceptStateOut,
    ConceptStateResponse,
    LearnerEvidenceListResponse,
    LearnerEvidenceOut,
    RecalculateOut,
    RecalculateResponse,
    SummaryOut,
    SummaryResponse,
    SyncOut,
    SyncResponse,
)
from app.repositories.learner_evidence_repository import LearnerEvidenceRepository
from app.repositories.learner_state_repository import LearnerStateRepository

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/knowledge/learner", tags=["knowledge-learner"])


def _link_out(link: KnowledgeConceptLink, name: str, label: str | None) -> ConceptLinkOut:
    return ConceptLinkOut(
        id=link.id,
        workspace_id=link.workspace_id,
        source_type=link.source_type,
        source_id=link.source_id,
        knowledge_node_id=link.knowledge_node_id,
        node_name=name,
        source_label=label,
        method=link.method,
        status=link.status,
        created_at=link.created_at,
    )


@router.post("/sync", response_model=SyncResponse)
async def sync_evidence(current_user: ActiveUser, db: DbSession) -> SyncResponse:
    """Ingest new quiz answers and flashcard reviews. Safe to repeat; nothing is counted twice."""
    result = await LearnerEvidenceService(db).sync(current_user.id)
    return SyncResponse(
        data=SyncOut(
            ingested=result["ingested"], remapped=result["remapped"], more=bool(result["more"])
        )
    )


@router.get("/summary", response_model=SummaryResponse)
async def evidence_summary(current_user: ActiveUser, db: DbSession) -> SummaryResponse:
    data = await LearnerEvidenceRepository(db).summary(current_user.id)
    return SummaryResponse(data=SummaryOut(**data))


@router.get("/evidence", response_model=LearnerEvidenceListResponse)
async def list_evidence(
    current_user: ActiveUser,
    db: DbSession,
    node_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
    unmapped: bool = False,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> LearnerEvidenceListResponse:
    rows, total = await LearnerEvidenceRepository(db).list_evidence(
        current_user.id,
        node_id=node_id,
        unmapped=unmapped,
        workspace_id=workspace_id,
        limit=limit,
        offset=offset,
    )
    return LearnerEvidenceListResponse(
        data=[LearnerEvidenceOut.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/links", response_model=ConceptLinkListResponse)
async def list_links(
    current_user: ActiveUser,
    db: DbSession,
    status: Literal["confirmed", "proposed", "rejected"] | None = "proposed",
    workspace_id: uuid.UUID | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> ConceptLinkListResponse:
    rows, total = await LearnerEvidenceRepository(db).list_links(
        current_user.id, status=status, workspace_id=workspace_id, limit=limit, offset=offset
    )
    return ConceptLinkListResponse(
        data=[_link_out(link, name, label) for link, name, label in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


async def _decide(
    link_id: uuid.UUID, status: str, current_user: ActiveUser, db: DbSession
) -> ConceptLinkResponse:
    link = await LearnerEvidenceService(db).decide_link(current_user.id, link_id, status)
    name, label = await LearnerEvidenceRepository(db).link_labels(current_user.id, link)
    return ConceptLinkResponse(data=_link_out(link, name, label))


@router.post("/links/{link_id}/confirm", response_model=ConceptLinkResponse)
async def confirm_link(
    link_id: uuid.UUID, current_user: ActiveUser, db: DbSession
) -> ConceptLinkResponse:
    return await _decide(link_id, "confirmed", current_user, db)


@router.post("/links/{link_id}/reject", response_model=ConceptLinkResponse)
async def reject_link(
    link_id: uuid.UUID, current_user: ActiveUser, db: DbSession
) -> ConceptLinkResponse:
    return await _decide(link_id, "rejected", current_user, db)


# mastery ─────────────────────────────────────────────────────────────────────


def _state_out(row: LearnerConceptState, name: str) -> ConceptStateOut:
    expl = row.explanation or {}
    return ConceptStateOut(
        knowledge_node_id=row.knowledge_node_id,
        workspace_id=row.workspace_id,
        node_name=name,
        state=row.state,
        mastery_estimate=None if row.mastery_estimate is None else float(row.mastery_estimate),
        confidence=float(row.confidence),
        evidence_count=row.evidence_count,
        last_evidence_at=row.last_evidence_at,
        next_review_at=row.next_review_at,
        calculation_version=row.calculation_version,
        explanation=str(expl.get("text", "")),
        explanation_facts=dict(expl.get("facts", {})),
    )


@router.get("/states", response_model=ConceptStateListResponse)
async def list_states(
    current_user: ActiveUser,
    db: DbSession,
    workspace_id: uuid.UUID | None = None,
    state: Literal[
        "NOT_ASSESSED", "INSUFFICIENT_EVIDENCE", "LEARNING", "DEVELOPING", "PROFICIENT", "STRONG"
    ]
    | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> ConceptStateListResponse:
    rows, total = await LearnerStateRepository(db).list_states(
        current_user.id, workspace_id=workspace_id, state=state, limit=limit, offset=offset
    )
    return ConceptStateListResponse(
        data=[_state_out(r, n) for r, n in rows], total=total, limit=limit, offset=offset
    )


@router.get("/states/{node_id}", response_model=ConceptStateResponse)
async def get_state(
    node_id: uuid.UUID, current_user: ActiveUser, db: DbSession
) -> ConceptStateResponse:
    """A concept with no evidence is NOT_ASSESSED with no score (never reported as weak)."""
    repo = LearnerStateRepository(db)
    nodes = await repo.nodes(current_user.id, [node_id])
    node = nodes.get(node_id)
    if node is None:
        raise NodeNotFoundError()
    row = await repo.get(current_user.id, node_id)
    if row is None:
        return ConceptStateResponse(
            data=ConceptStateOut(
                knowledge_node_id=node.id,
                workspace_id=node.workspace_id,
                node_name=node.name,
                state="NOT_ASSESSED",
                mastery_estimate=None,
                confidence=0.0,
                evidence_count=0,
                last_evidence_at=None,
                next_review_at=None,
                calculation_version=CALCULATION_VERSION,
                explanation=f"{node.name} has not been assessed yet. "
                "There is no quiz or flashcard evidence for it.",
                explanation_facts={"evidence_count": 0},
            )
        )
    return ConceptStateResponse(data=_state_out(row, node.name))


@router.post("/recalculate", response_model=RecalculateResponse, status_code=202)
async def recalculate(current_user: ActiveUser, db: DbSession) -> RecalculateResponse:
    """Recalculate every concept state (for example after the model version changes). Handed to the
    worker when one is available; otherwise done in this request."""
    from app.core.config import get_settings

    if get_settings().celery_broker_url:
        from app.ingestion.worker import celery_app

        try:
            celery_app.send_task(RECALC_TASK, args=[str(current_user.id)])
            return RecalculateResponse(data=RecalculateOut(mode="queued"))
        except Exception as exc:  # broker down: fall through and do it here
            logger.warning("recalculate_dispatch_failed", error_type=type(exc).__name__)
    count = await MasteryService(db).recalculate(current_user.id)
    await db.commit()
    return RecalculateResponse(data=RecalculateOut(mode="done", states=count))
