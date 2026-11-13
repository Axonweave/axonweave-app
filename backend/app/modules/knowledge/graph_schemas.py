"""Request and response schemas for the knowledge graph APIs (Milestone 6.3). All input is
validated here; the client never supplies a user id, and ids it does supply are ownership-checked
in the service."""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.models.knowledge import NODE_TYPES, RELATIONSHIP_TYPES

NodeTypeLiteral = Literal[NODE_TYPES]  # type: ignore[valid-type]
RelationshipTypeLiteral = Literal[RELATIONSHIP_TYPES]  # type: ignore[valid-type]
DifficultyLiteral = Literal["introductory", "intermediate", "advanced"]


def _clean(value: str) -> str:
    return " ".join(value.split())


Name = Annotated[str, Field(min_length=2, max_length=200), AfterValidator(_clean)]
Alias = Annotated[str, Field(min_length=1, max_length=200), AfterValidator(_clean)]


# requests ────────────────────────────────────────────────────────────────────


class NodeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: uuid.UUID
    subject_id: uuid.UUID | None = None
    chapter_id: uuid.UUID | None = None
    name: Name
    node_type: NodeTypeLiteral = "concept"
    description: str | None = Field(default=None, max_length=1000)
    definition: str | None = Field(default=None, max_length=2000)
    difficulty: DifficultyLiteral | None = None
    aliases: list[Alias] = Field(default_factory=list, max_length=8)


class NodePatch(BaseModel):
    """Only the fields that are sent change. Any edit marks the concept as user-edited, so a later
    extraction never overwrites it (spec 9.5)."""

    model_config = ConfigDict(extra="forbid")

    name: Name | None = None
    node_type: NodeTypeLiteral | None = None
    description: str | None = Field(default=None, max_length=1000)
    definition: str | None = Field(default=None, max_length=2000)
    difficulty: DifficultyLiteral | None = None
    aliases: list[Alias] | None = Field(default=None, max_length=8)


class EdgeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_node_id: uuid.UUID
    target_node_id: uuid.UUID
    relationship_type: RelationshipTypeLiteral
    description: str | None = Field(default=None, max_length=500)


class EdgePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relationship_type: RelationshipTypeLiteral | None = None
    description: str | None = Field(default=None, max_length=500)


class MergeRequest(BaseModel):
    """`merged_id` is folded into `survivor_id` and then removed (an audit row is kept)."""

    model_config = ConfigDict(extra="forbid")

    survivor_id: uuid.UUID
    merged_id: uuid.UUID


class CandidateResolve(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["merge", "keep_separate", "related", "ignore"]
    # Required for "merge": which of the two concepts is kept.
    survivor_id: uuid.UUID | None = None


# responses ───────────────────────────────────────────────────────────────────


class NodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    subject_id: uuid.UUID | None
    chapter_id: uuid.UUID | None
    name: str
    description: str | None
    definition: str | None
    node_type: str
    difficulty: str | None
    origin: str
    edited_by_user: bool
    confidence: float | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime
    aliases: list[str] = Field(default_factory=list)
    evidence_count: int = 0
    degree: int = 0


class EdgeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    source_node_id: uuid.UUID
    target_node_id: uuid.UUID
    relationship_type: str
    description: str | None
    confidence: float | None
    statement_kind: str
    origin: str
    created_at: datetime


class RelatedNodeOut(BaseModel):
    node: NodeOut
    edge: EdgeOut


class NodeDetailOut(NodeOut):
    prerequisites: list[RelatedNodeOut] = Field(default_factory=list)
    dependents: list[RelatedNodeOut] = Field(default_factory=list)
    related: list[RelatedNodeOut] = Field(default_factory=list)


class GraphOut(BaseModel):
    nodes: list[NodeOut]
    edges: list[EdgeOut]
    # True when the node or edge cap stopped the view: more exists than is shown.
    truncated: bool = False
    node_limit: int
    total_nodes: int | None = None


class GraphOverviewOut(BaseModel):
    total_nodes: int
    total_edges: int
    node_types: dict[str, int]
    graph: GraphOut


class EvidenceOut(BaseModel):
    id: uuid.UUID
    knowledge_node_id: uuid.UUID | None
    knowledge_edge_id: uuid.UUID | None
    # "document" evidence has the document fields; "web" evidence has an https link instead (the
    # server never fetches it, and the browser opens it in a new tab with no referrer).
    source_kind: Literal["document", "web"] = "document"
    source_url: str | None = None
    source_title: str | None = None
    document_id: uuid.UUID | None
    document_name: str | None
    document_version_id: uuid.UUID | None
    chunk_index: int | None
    chunk_id: uuid.UUID | None
    page_number: int | None
    slide_number: int | None
    quote: str
    evidence_type: str
    extraction_method: str
    confidence: float | None
    # True when the document was replaced since: the quote may no longer match the current text.
    stale: bool
    created_at: datetime


class CandidateOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    status: str
    signals: list[str]
    node_a: NodeOut
    node_b: NodeOut
    created_at: datetime


# envelopes ───────────────────────────────────────────────────────────────────


class ClearGraphRequest(BaseModel):
    """Delete every concept of one subject. `confirm` must be true (irreversible)."""

    model_config = ConfigDict(extra="forbid")

    subject_id: uuid.UUID
    confirm: Literal[True]


class ClearGraphOut(BaseModel):
    concepts: int
    relationships: int


class ClearGraphResponse(BaseModel):
    success: bool = True
    data: ClearGraphOut


class NodeResponse(BaseModel):
    success: bool = True
    data: NodeOut


class NodeDetailResponse(BaseModel):
    success: bool = True
    data: NodeDetailOut


class NodeListResponse(BaseModel):
    success: bool = True
    data: list[NodeOut]
    total: int
    limit: int
    offset: int


class EdgeResponse(BaseModel):
    success: bool = True
    data: EdgeOut


class GraphResponse(BaseModel):
    success: bool = True
    data: GraphOut


class GraphOverviewResponse(BaseModel):
    success: bool = True
    data: GraphOverviewOut


class EvidenceListResponse(BaseModel):
    success: bool = True
    data: list[EvidenceOut]
    total: int
    limit: int
    offset: int


class CandidateListResponse(BaseModel):
    success: bool = True
    data: list[CandidateOut]
    total: int
    limit: int
    offset: int


class CandidateResolveResponse(BaseModel):
    success: bool = True
    data: dict[str, Any]
