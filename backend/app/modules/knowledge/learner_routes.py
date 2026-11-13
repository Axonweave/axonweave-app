"""Learner evidence routes (Milestone 6.5). Everything is scoped to the signed-in user; a link id
that is not theirs is a 404. Writes are covered by the app's CSRF protection (D-04)."""

import uuid
from typing import Literal

from fastapi import APIRouter, Query

from app.core.dependencies import ActiveUser, DbSession
from app.knowledge.learner_evidence import LearnerEvidenceService
from app.models.learner import KnowledgeConceptLink
from app.modules.knowledge.learner_schemas import (
    ConceptLinkListResponse,
    ConceptLinkOut,
    ConceptLinkResponse,
    LearnerEvidenceListResponse,
    LearnerEvidenceOut,
    SummaryOut,
    SummaryResponse,
    SyncOut,
    SyncResponse,
)
from app.repositories.learner_evidence_repository import LearnerEvidenceRepository

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
