"""Knowledge graph routes (Milestone 6.3, spec 11.2). Every route needs an active session; ownership
is checked in the service and a non-owned id is a 404. Mutating routes are covered by the app's CSRF
protection like every cookie-authenticated write (D-04)."""

import uuid
from typing import Literal

from fastapi import APIRouter, Query

from app.core.dependencies import ActiveUser, DbSession
from app.models.knowledge import KnowledgeEvidence
from app.modules.knowledge.graph_schemas import (
    CandidateListResponse,
    CandidateOut,
    CandidateResolve,
    CandidateResolveResponse,
    EdgeCreate,
    EdgeOut,
    EdgePatch,
    EdgeResponse,
    EvidenceListResponse,
    EvidenceOut,
    GraphOut,
    GraphOverviewOut,
    GraphOverviewResponse,
    GraphResponse,
    MergeRequest,
    NodeCreate,
    NodeDetailOut,
    NodeDetailResponse,
    NodeListResponse,
    NodeOut,
    NodePatch,
    NodeResponse,
    NodeTypeLiteral,
    RelationshipTypeLiteral,
)
from app.modules.knowledge.graph_service import (
    DEFAULT_NODE_LIMIT,
    MAX_DEPTH,
    MAX_NODE_LIMIT,
    KnowledgeGraphService,
)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

_MAX_LIMIT = 100


def _evidence_out(rows: list[tuple[KnowledgeEvidence, str]]) -> list[EvidenceOut]:
    return [
        EvidenceOut(
            id=ev.id,
            knowledge_node_id=ev.knowledge_node_id,
            knowledge_edge_id=ev.knowledge_edge_id,
            document_id=ev.document_id,
            document_name=name,
            document_version_id=ev.document_version_id,
            chunk_index=ev.chunk_index,
            chunk_id=ev.chunk_id,
            page_number=ev.page_number,
            slide_number=ev.slide_number,
            quote=ev.quote,
            evidence_type=ev.evidence_type,
            extraction_method=ev.extraction_method,
            confidence=float(ev.confidence) if ev.confidence is not None else None,
            stale=ev.stale,
            created_at=ev.created_at,
        )
        for ev, name in rows
    ]


# graph views ─────────────────────────────────────────────────────────────────


@router.get("/graph", response_model=GraphResponse)
async def get_graph(
    current_user: ActiveUser,
    db: DbSession,
    workspace_id: uuid.UUID | None = None,
    subject_id: uuid.UUID | None = None,
    node_type: NodeTypeLiteral | None = None,
    q: str | None = Query(None, max_length=100),
    relationship_types: list[RelationshipTypeLiteral] | None = Query(None),
    limit: int = Query(DEFAULT_NODE_LIMIT, ge=1, le=MAX_NODE_LIMIT),
) -> GraphResponse:
    data = await KnowledgeGraphService(db).graph(
        current_user,
        workspace_id=workspace_id,
        subject_id=subject_id,
        node_type=node_type,
        q=q,
        relationship_types=relationship_types,
        limit=limit,
    )
    return GraphResponse(data=GraphOut.model_validate(data))


@router.get("/graph/overview", response_model=GraphOverviewResponse)
async def get_graph_overview(
    current_user: ActiveUser,
    db: DbSession,
    workspace_id: uuid.UUID | None = None,
    subject_id: uuid.UUID | None = None,
) -> GraphOverviewResponse:
    data = await KnowledgeGraphService(db).overview(
        current_user, workspace_id=workspace_id, subject_id=subject_id
    )
    return GraphOverviewResponse(data=GraphOverviewOut.model_validate(data))


@router.get("/graph/expand", response_model=GraphResponse)
async def expand_graph(
    node_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
    depth: int = Query(1, ge=1, le=MAX_DEPTH),
    limit: int = Query(DEFAULT_NODE_LIMIT, ge=2, le=MAX_NODE_LIMIT),
    relationship_types: list[RelationshipTypeLiteral] | None = Query(None),
) -> GraphResponse:
    data = await KnowledgeGraphService(db).expand(
        current_user,
        node_id,
        depth=depth,
        limit=limit,
        relationship_types=relationship_types,
    )
    return GraphResponse(data=GraphOut.model_validate(data))


# nodes ───────────────────────────────────────────────────────────────────────


@router.get("/nodes", response_model=NodeListResponse)
async def list_nodes(
    current_user: ActiveUser,
    db: DbSession,
    workspace_id: uuid.UUID | None = None,
    subject_id: uuid.UUID | None = None,
    node_type: NodeTypeLiteral | None = None,
    q: str | None = Query(None, max_length=100),
    archived: bool = False,
    sort: Literal["name", "created_at", "updated_at"] = "name",
    order: Literal["asc", "desc"] = "asc",
    limit: int = Query(20, ge=1, le=_MAX_LIMIT),
    offset: int = Query(0, ge=0),
) -> NodeListResponse:
    rows, total = await KnowledgeGraphService(db).list_nodes(
        current_user,
        workspace_id=workspace_id,
        subject_id=subject_id,
        node_type=node_type,
        q=q,
        archived=archived,
        sort=sort,
        descending=order == "desc",
        limit=limit,
        offset=offset,
    )
    return NodeListResponse(
        data=[NodeOut.model_validate(r) for r in rows], total=total, limit=limit, offset=offset
    )


@router.post("/nodes", response_model=NodeResponse, status_code=201)
async def create_node(body: NodeCreate, current_user: ActiveUser, db: DbSession) -> NodeResponse:
    data = await KnowledgeGraphService(db).create_node(current_user, body)
    return NodeResponse(data=NodeOut.model_validate(data))


# Declared before `/nodes/{node_id}` so "merge" is never read as an id.
@router.post("/nodes/merge", response_model=NodeResponse)
async def merge_nodes(body: MergeRequest, current_user: ActiveUser, db: DbSession) -> NodeResponse:
    data = await KnowledgeGraphService(db).merge(current_user, body.survivor_id, body.merged_id)
    return NodeResponse(data=NodeOut.model_validate(data))


@router.get("/nodes/{node_id}", response_model=NodeDetailResponse)
async def get_node(
    node_id: uuid.UUID, current_user: ActiveUser, db: DbSession
) -> NodeDetailResponse:
    data = await KnowledgeGraphService(db).get_node_detail(current_user, node_id)
    return NodeDetailResponse(data=NodeDetailOut.model_validate(data))


@router.patch("/nodes/{node_id}", response_model=NodeResponse)
async def update_node(
    node_id: uuid.UUID, body: NodePatch, current_user: ActiveUser, db: DbSession
) -> NodeResponse:
    data = await KnowledgeGraphService(db).update_node(current_user, node_id, body)
    return NodeResponse(data=NodeOut.model_validate(data))


@router.delete("/nodes/{node_id}", status_code=204)
async def delete_node(node_id: uuid.UUID, current_user: ActiveUser, db: DbSession) -> None:
    await KnowledgeGraphService(db).delete_node(current_user, node_id)


@router.post("/nodes/{node_id}/archive", status_code=204)
async def archive_node(node_id: uuid.UUID, current_user: ActiveUser, db: DbSession) -> None:
    await KnowledgeGraphService(db).archive_node(current_user, node_id)


@router.post("/nodes/{node_id}/restore", response_model=NodeResponse)
async def restore_node(node_id: uuid.UUID, current_user: ActiveUser, db: DbSession) -> NodeResponse:
    data = await KnowledgeGraphService(db).restore_node(current_user, node_id)
    return NodeResponse(data=NodeOut.model_validate(data))


@router.get("/nodes/{node_id}/evidence", response_model=EvidenceListResponse)
async def get_node_evidence(
    node_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
    include_stale: bool = False,
    limit: int = Query(20, ge=1, le=_MAX_LIMIT),
    offset: int = Query(0, ge=0),
) -> EvidenceListResponse:
    rows, total = await KnowledgeGraphService(db).node_evidence(
        current_user, node_id, include_stale=include_stale, limit=limit, offset=offset
    )
    return EvidenceListResponse(data=_evidence_out(rows), total=total, limit=limit, offset=offset)


# relationships ───────────────────────────────────────────────────────────────


@router.post("/relationships", response_model=EdgeResponse, status_code=201)
async def create_relationship(
    body: EdgeCreate, current_user: ActiveUser, db: DbSession
) -> EdgeResponse:
    edge = await KnowledgeGraphService(db).create_edge(current_user, body)
    return EdgeResponse(data=EdgeOut.model_validate(edge))


@router.patch("/relationships/{relationship_id}", response_model=EdgeResponse)
async def update_relationship(
    relationship_id: uuid.UUID, body: EdgePatch, current_user: ActiveUser, db: DbSession
) -> EdgeResponse:
    edge = await KnowledgeGraphService(db).update_edge(current_user, relationship_id, body)
    return EdgeResponse(data=EdgeOut.model_validate(edge))


@router.delete("/relationships/{relationship_id}", status_code=204)
async def delete_relationship(
    relationship_id: uuid.UUID, current_user: ActiveUser, db: DbSession
) -> None:
    await KnowledgeGraphService(db).delete_edge(current_user, relationship_id)


@router.get("/relationships/{relationship_id}/evidence", response_model=EvidenceListResponse)
async def get_relationship_evidence(
    relationship_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
    include_stale: bool = False,
    limit: int = Query(20, ge=1, le=_MAX_LIMIT),
    offset: int = Query(0, ge=0),
) -> EvidenceListResponse:
    rows, total = await KnowledgeGraphService(db).edge_evidence(
        current_user, relationship_id, include_stale=include_stale, limit=limit, offset=offset
    )
    return EvidenceListResponse(data=_evidence_out(rows), total=total, limit=limit, offset=offset)


# duplicate review ────────────────────────────────────────────────────────────


@router.get("/duplicates", response_model=CandidateListResponse)
async def list_duplicate_candidates(
    current_user: ActiveUser,
    db: DbSession,
    workspace_id: uuid.UUID | None = None,
    status: Literal["open", "merged", "kept_separate", "related", "ignored"] | None = "open",
    limit: int = Query(20, ge=1, le=_MAX_LIMIT),
    offset: int = Query(0, ge=0),
) -> CandidateListResponse:
    rows, total = await KnowledgeGraphService(db).list_candidates(
        current_user, workspace_id=workspace_id, status=status, limit=limit, offset=offset
    )
    return CandidateListResponse(
        data=[CandidateOut.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/duplicates/{candidate_id}/resolve", response_model=CandidateResolveResponse)
async def resolve_duplicate_candidate(
    candidate_id: uuid.UUID, body: CandidateResolve, current_user: ActiveUser, db: DbSession
) -> CandidateResolveResponse:
    data = await KnowledgeGraphService(db).resolve_candidate(
        current_user, candidate_id, body.action, body.survivor_id
    )
    return CandidateResolveResponse(data=data)
