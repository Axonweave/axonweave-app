"""Knowledge graph service (Milestone 6.3): concepts, relationships, evidence, bounded traversal,
merging and duplicate review. Business rules live here; SQL lives in the repositories.

Ownership (CLAUDE.md rules 1 to 3): every id from the client is resolved through a query scoped by
`user_id`; a node, edge, workspace, subject or chapter that is not the caller's is a 404, exactly
like a missing one. Relationships can only join two concepts of one workspace (also enforced by
composite foreign keys). Traversal is bounded by depth and by node and edge caps."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.errors import (
    AliasConflictError,
    CandidateNotFoundError,
    DuplicateConceptError,
    DuplicateRelationshipError,
    EdgeNotFoundError,
    InvalidCandidateActionError,
    InvalidMergeError,
    InvalidRelationshipError,
    NodeNotArchivedError,
    NodeNotFoundError,
    ScopeNotFoundError,
)
from app.knowledge.mastery_service import MasteryService
from app.knowledge.normalise import normalise_name
from app.models.knowledge import SYMMETRIC_TYPES, KnowledgeEdge, KnowledgeNode
from app.models.user import User
from app.repositories.chapter_repository import ChapterRepository
from app.repositories.knowledge_graph_repository import KnowledgeGraphRepository
from app.repositories.knowledge_repository import KnowledgeRepository
from app.repositories.learner_evidence_repository import LearnerEvidenceRepository
from app.repositories.subject_repository import SubjectRepository
from app.repositories.workspace_repository import WorkspaceRepository

logger = structlog.get_logger(__name__)

MAX_DEPTH = 3
DEFAULT_NODE_LIMIT = 60
MAX_NODE_LIMIT = 200
MAX_EDGE_LIMIT = 600
SIDE_LIST_LIMIT = 50
PREREQUISITE_TYPES = ("PREREQUISITE_OF", "DEPENDS_ON")


def _now() -> datetime:
    return datetime.now(UTC)


def _ordered(source: uuid.UUID, target: uuid.UUID, rel: str) -> tuple[uuid.UUID, uuid.UUID]:
    """Symmetric relationships are stored once, smaller id first."""
    if rel in SYMMETRIC_TYPES and str(target) < str(source):
        return target, source
    return source, target


class KnowledgeGraphService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._g = KnowledgeGraphRepository(db)
        self._k = KnowledgeRepository(db)

    # shaping ─────────────────────────────────────────────────────────────────

    async def _decorate(
        self, user_id: uuid.UUID, nodes: Sequence[KnowledgeNode]
    ) -> list[dict[str, Any]]:
        """Nodes plus aliases, evidence count and degree in three batched queries (no N+1)."""
        ids = [n.id for n in nodes]
        aliases = await self._g.aliases_for(user_id, ids)
        evidence = await self._g.evidence_counts(user_id, ids)
        degree = await self._g.degrees(user_id, ids)
        out = []
        for n in nodes:
            out.append(
                {
                    **{c: getattr(n, c) for c in _NODE_FIELDS},
                    "aliases": aliases.get(n.id, []),
                    "evidence_count": evidence.get(n.id, 0),
                    "degree": degree.get(n.id, 0),
                }
            )
        return out

    # scope checks ────────────────────────────────────────────────────────────

    async def _check_scope(
        self,
        user: User,
        workspace_id: uuid.UUID,
        subject_id: uuid.UUID | None,
        chapter_id: uuid.UUID | None,
    ) -> None:
        if await WorkspaceRepository(self._db).get_for_user(workspace_id, user.id) is None:
            raise ScopeNotFoundError()
        if subject_id is not None:
            subject = await SubjectRepository(self._db).get_for_workspace(
                subject_id=subject_id, workspace_id=workspace_id
            )
            if subject is None:
                raise ScopeNotFoundError()
        if chapter_id is not None:
            if subject_id is None:
                raise ScopeNotFoundError()
            chapter = await ChapterRepository(self._db).get_for_subject(
                chapter_id=chapter_id, subject_id=subject_id
            )
            if chapter is None:
                raise ScopeNotFoundError()

    async def _node(
        self, user: User, node_id: uuid.UUID, *, archived_ok: bool = False
    ) -> KnowledgeNode:
        node = await self._g.get_node(user.id, node_id, include_archived=archived_ok)
        if node is None:
            raise NodeNotFoundError()
        return node

    # nodes ───────────────────────────────────────────────────────────────────

    async def list_nodes(
        self,
        user: User,
        *,
        workspace_id: uuid.UUID | None,
        subject_id: uuid.UUID | None,
        node_type: str | None,
        q: str | None,
        archived: bool,
        sort: str,
        descending: bool,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int]:
        nodes, total = await self._g.list_nodes(
            user.id,
            workspace_id=workspace_id,
            subject_id=subject_id,
            node_type=node_type,
            q=q.strip() if q else None,
            archived=archived,
            sort=sort,
            descending=descending,
            limit=limit,
            offset=offset,
        )
        return await self._decorate(user.id, nodes), total

    async def create_node(self, user: User, body: Any) -> dict[str, Any]:
        await self._check_scope(user, body.workspace_id, body.subject_id, body.chapter_id)
        norm = normalise_name(body.name)
        if not norm:
            raise DuplicateConceptError()  # a name of only punctuation is not a usable key
        try:
            async with self._db.begin_nested():
                node = self._k.add_node(
                    user_id=user.id,
                    workspace_id=body.workspace_id,
                    subject_id=body.subject_id,
                    chapter_id=body.chapter_id,
                    name=body.name,
                    normalised_name=norm,
                    description=body.description,
                    definition=body.definition,
                    node_type=body.node_type,
                    difficulty=body.difficulty,
                    attributes={},
                    origin="user",
                    edited_by_user=True,
                )
                await self._db.flush()
        except IntegrityError:
            raise DuplicateConceptError() from None
        await self._set_aliases(user, node, body.aliases)
        await self._db.commit()
        return (await self._decorate(user.id, [node]))[0]

    async def get_node_detail(self, user: User, node_id: uuid.UUID) -> dict[str, Any]:
        node = await self._node(user, node_id)
        base = (await self._decorate(user.id, [node]))[0]
        prereq = await self._g.related_nodes(
            user.id,
            node_id,
            relationship_types=("PREREQUISITE_OF",),
            as_source=False,
            limit=SIDE_LIST_LIMIT,
        ) + await self._g.related_nodes(
            user.id,
            node_id,
            relationship_types=("DEPENDS_ON",),
            as_source=True,
            limit=SIDE_LIST_LIMIT,
        )
        dependents = await self._g.related_nodes(
            user.id,
            node_id,
            relationship_types=("PREREQUISITE_OF",),
            as_source=True,
            limit=SIDE_LIST_LIMIT,
        ) + await self._g.related_nodes(
            user.id,
            node_id,
            relationship_types=("DEPENDS_ON",),
            as_source=False,
            limit=SIDE_LIST_LIMIT,
        )
        other_types = tuple(
            t
            for t in (
                "IS_A",
                "PART_OF",
                "RELATED_TO",
                "CONTRASTS_WITH",
                "USES",
                "APPLIED_IN",
                "EXAMPLE_OF",
            )
        )
        related = await self._g.related_nodes(
            user.id, node_id, relationship_types=other_types, as_source=True, limit=SIDE_LIST_LIMIT
        ) + await self._g.related_nodes(
            user.id, node_id, relationship_types=other_types, as_source=False, limit=SIDE_LIST_LIMIT
        )
        base["prerequisites"] = await self._pairs(user.id, prereq[:SIDE_LIST_LIMIT])
        base["dependents"] = await self._pairs(user.id, dependents[:SIDE_LIST_LIMIT])
        base["related"] = await self._pairs(user.id, related[:SIDE_LIST_LIMIT])
        return base

    async def _pairs(
        self, user_id: uuid.UUID, pairs: Sequence[tuple[KnowledgeNode, KnowledgeEdge]]
    ) -> list[dict[str, Any]]:
        decorated = {d["id"]: d for d in await self._decorate(user_id, [n for n, _ in pairs])}
        return [{"node": decorated[n.id], "edge": e} for n, e in pairs]

    async def update_node(self, user: User, node_id: uuid.UUID, body: Any) -> dict[str, Any]:
        node = await self._node(user, node_id)
        sent = body.model_fields_set
        try:
            async with self._db.begin_nested():
                if "name" in sent and body.name is not None:
                    norm = normalise_name(body.name)
                    if not norm:
                        raise DuplicateConceptError()
                    node.name, node.normalised_name = body.name, norm
                if "node_type" in sent and body.node_type is not None:
                    node.node_type = body.node_type
                if "description" in sent:
                    node.description = body.description
                if "definition" in sent:
                    node.definition = body.definition
                if "difficulty" in sent:
                    node.difficulty = body.difficulty
                if sent:
                    node.edited_by_user = True  # re-extraction never overwrites a user edit
                await self._db.flush()
        except IntegrityError:
            raise DuplicateConceptError() from None
        if "aliases" in sent and body.aliases is not None:
            await self._set_aliases(user, node, body.aliases)
        await self._db.commit()
        await self._db.refresh(node)
        return (await self._decorate(user.id, [node]))[0]

    async def _set_aliases(self, user: User, node: KnowledgeNode, aliases: Sequence[str]) -> None:
        """Replace the alias list. An alias that is another concept's name or alias is refused:
        merging concepts is an explicit, reviewable action, never a side effect of an edit."""
        wanted: dict[str, str] = {}
        for alias in aliases:
            key = normalise_name(alias)
            if key and key != node.normalised_name:
                wanted.setdefault(key, alias)
        for key in wanted:
            owner = await self._k.alias_owner(user.id, node.workspace_id, key)
            if owner is not None and owner != node.id:
                raise AliasConflictError()
            for other in await self._k.nodes_named(user.id, node.workspace_id, key):
                if other.id != node.id:
                    raise AliasConflictError()
        current = {a.normalised_alias: a for a in await self._g.alias_rows(user.id, node.id)}
        for key, row in current.items():
            if key not in wanted:
                await self._g.delete_alias(user.id, row.id)
        for key, alias in wanted.items():
            if key not in current:
                self._k.add_alias(
                    user_id=user.id,
                    workspace_id=node.workspace_id,
                    knowledge_node_id=node.id,
                    alias=alias,
                    normalised_alias=key,
                )
        await self._db.flush()

    async def archive_node(self, user: User, node_id: uuid.UUID) -> None:
        await self._node(user, node_id)
        await self._g.archive_node(user.id, node_id, _now())
        await self._db.commit()

    async def restore_node(self, user: User, node_id: uuid.UUID) -> dict[str, Any]:
        node = await self._node(user, node_id, archived_ok=True)
        if node.archived_at is None:
            return (await self._decorate(user.id, [node]))[0]
        try:
            async with self._db.begin_nested():
                node.archived_at = None
                await self._db.flush()
        except IntegrityError:  # an active concept with that name and type exists now
            raise DuplicateConceptError() from None
        await self._db.commit()
        await self._db.refresh(node)  # updated_at is set by the database
        return (await self._decorate(user.id, [node]))[0]

    async def delete_node(self, user: User, node_id: uuid.UUID) -> None:
        """Permanent and explicit: only an archived concept can be deleted. Its relationships,
        aliases and evidence are deleted with it."""
        node = await self._node(user, node_id, archived_ok=True)
        if node.archived_at is None:
            raise NodeNotArchivedError()
        await self._g.delete_node(user.id, node_id)
        await self._db.commit()

    # relationships ───────────────────────────────────────────────────────────

    async def create_edge(self, user: User, body: Any, *, origin: str = "user") -> KnowledgeEdge:
        if body.source_node_id == body.target_node_id:
            raise InvalidRelationshipError()
        source = await self._node(user, body.source_node_id)
        target = await self._node(user, body.target_node_id)
        if source.workspace_id != target.workspace_id:
            raise InvalidRelationshipError()
        src, tgt = _ordered(source.id, target.id, body.relationship_type)
        if await self._k.find_edge(user.id, src, tgt, body.relationship_type) is not None:
            raise DuplicateRelationshipError()
        try:
            async with self._db.begin_nested():
                edge = self._k.add_edge(
                    user_id=user.id,
                    workspace_id=source.workspace_id,
                    source_node_id=src,
                    target_node_id=tgt,
                    relationship_type=body.relationship_type,
                    description=body.description,
                    confidence=None,
                    statement_kind="stated",
                    origin=origin,
                )
                await self._db.flush()
        except IntegrityError:
            raise DuplicateRelationshipError() from None
        await self._db.commit()
        await self._db.refresh(edge)
        return edge

    async def update_edge(self, user: User, edge_id: uuid.UUID, body: Any) -> KnowledgeEdge:
        edge = await self._g.get_edge(user.id, edge_id)
        if edge is None:
            raise EdgeNotFoundError()
        sent = body.model_fields_set
        try:
            async with self._db.begin_nested():
                if "relationship_type" in sent and body.relationship_type is not None:
                    src, tgt = _ordered(
                        edge.source_node_id, edge.target_node_id, body.relationship_type
                    )
                    edge.source_node_id, edge.target_node_id = src, tgt
                    edge.relationship_type = body.relationship_type
                if "description" in sent:
                    edge.description = body.description
                if sent:
                    edge.origin = "user"  # the user vouches for it now
                await self._db.flush()
        except IntegrityError:
            raise DuplicateRelationshipError() from None
        await self._db.commit()
        await self._db.refresh(edge)
        return edge

    async def delete_edge(self, user: User, edge_id: uuid.UUID) -> None:
        if await self._g.get_edge(user.id, edge_id) is None:
            raise EdgeNotFoundError()
        await self._g.delete_edge(user.id, edge_id)
        await self._db.commit()

    # evidence ────────────────────────────────────────────────────────────────

    async def node_evidence(
        self, user: User, node_id: uuid.UUID, *, include_stale: bool, limit: int, offset: int
    ) -> tuple[list[tuple[Any, str]], int]:
        await self._node(user, node_id)
        return await self._g.list_evidence(
            user.id,
            node_id=node_id,
            edge_id=None,
            include_stale=include_stale,
            limit=limit,
            offset=offset,
        )

    async def edge_evidence(
        self, user: User, edge_id: uuid.UUID, *, include_stale: bool, limit: int, offset: int
    ) -> tuple[list[tuple[Any, str]], int]:
        if await self._g.get_edge(user.id, edge_id) is None:
            raise EdgeNotFoundError()
        return await self._g.list_evidence(
            user.id,
            node_id=None,
            edge_id=edge_id,
            include_stale=include_stale,
            limit=limit,
            offset=offset,
        )

    # graph views ─────────────────────────────────────────────────────────────

    async def _graph(
        self,
        user: User,
        nodes: Sequence[KnowledgeNode],
        *,
        types: Sequence[str] | None,
        node_limit: int,
        truncated: bool,
        total_nodes: int | None,
    ) -> dict[str, Any]:
        edges = await self._g.edges_among(
            user.id, [n.id for n in nodes], types=types, limit=MAX_EDGE_LIMIT + 1
        )
        if len(edges) > MAX_EDGE_LIMIT:
            edges, truncated = edges[:MAX_EDGE_LIMIT], True
        return {
            "nodes": await self._decorate(user.id, nodes),
            "edges": edges,
            "truncated": truncated,
            "node_limit": node_limit,
            "total_nodes": total_nodes,
        }

    async def graph(
        self,
        user: User,
        *,
        workspace_id: uuid.UUID | None,
        subject_id: uuid.UUID | None,
        node_type: str | None,
        q: str | None,
        relationship_types: Sequence[str] | None,
        limit: int,
    ) -> dict[str, Any]:
        """A bounded view: the most connected concepts of the scope and the relationships among
        them. Never the whole graph (spec 12.5)."""
        limit = min(max(limit, 1), MAX_NODE_LIMIT)
        nodes = await self._g.top_nodes_by_degree(
            user.id,
            workspace_id=workspace_id,
            subject_id=subject_id,
            node_type=node_type,
            q=q.strip() if q else None,
            limit=limit,
        )
        total = await self._g.count_nodes(user.id, workspace_id, subject_id)
        return await self._graph(
            user,
            nodes,
            types=relationship_types,
            node_limit=limit,
            truncated=total > len(nodes),
            total_nodes=total,
        )

    async def overview(
        self, user: User, *, workspace_id: uuid.UUID | None, subject_id: uuid.UUID | None
    ) -> dict[str, Any]:
        graph = await self.graph(
            user,
            workspace_id=workspace_id,
            subject_id=subject_id,
            node_type=None,
            q=None,
            relationship_types=None,
            limit=DEFAULT_NODE_LIMIT,
        )
        return {
            "total_nodes": await self._g.count_nodes(user.id, workspace_id, subject_id),
            "total_edges": await self._g.count_edges(user.id, workspace_id),
            "node_types": await self._g.type_counts(user.id, workspace_id, subject_id),
            "graph": graph,
        }

    async def expand(
        self,
        user: User,
        node_id: uuid.UUID,
        *,
        depth: int,
        limit: int,
        relationship_types: Sequence[str] | None,
    ) -> dict[str, Any]:
        """Breadth-first expansion around one concept: one batched query per level, at most
        `MAX_DEPTH` levels and `limit` nodes. `truncated` says when the caps cut the result."""
        root = await self._node(user, node_id)
        depth = min(max(depth, 1), MAX_DEPTH)
        limit = min(max(limit, 2), MAX_NODE_LIMIT)
        visited: dict[uuid.UUID, KnowledgeNode] = {root.id: root}
        frontier = [root.id]
        truncated = False
        for _ in range(depth):
            if not frontier:
                break
            edges = await self._g.edges_touching(
                user.id, frontier, types=relationship_types, limit=MAX_EDGE_LIMIT + 1
            )
            if len(edges) > MAX_EDGE_LIMIT:
                edges, truncated = edges[:MAX_EDGE_LIMIT], True
            new_ids: list[uuid.UUID] = []
            for e in edges:
                for end in (e.source_node_id, e.target_node_id):
                    if end not in visited and end not in new_ids:
                        new_ids.append(end)
            room = limit - len(visited)
            if len(new_ids) > room:
                new_ids, truncated = new_ids[: max(room, 0)], True
            found = await self._g.get_nodes(user.id, new_ids)  # archived concepts are skipped
            frontier = []
            for n in sorted(found, key=lambda x: new_ids.index(x.id)):
                visited[n.id] = n
                frontier.append(n.id)
            if len(visited) >= limit:
                # Stopped at the cap: say so if anything beyond it exists (one more cheap query).
                beyond = await self._g.edges_touching(
                    user.id, frontier, types=relationship_types, limit=MAX_EDGE_LIMIT
                )
                if any(
                    end not in visited
                    for e in beyond
                    for end in (e.source_node_id, e.target_node_id)
                ):
                    truncated = True
                break
        return await self._graph(
            user,
            list(visited.values()),
            types=relationship_types,
            node_limit=limit,
            truncated=truncated,
            total_nodes=None,
        )

    # merge ───────────────────────────────────────────────────────────────────

    async def merge(
        self, user: User, survivor_id: uuid.UUID, merged_id: uuid.UUID
    ) -> dict[str, Any]:
        """Fold `merged` into `survivor` in one transaction: aliases, evidence and relationships
        move over (duplicates and self-loops are dropped), blanks are filled, an audit row is kept
        and the merged concept is removed. Learner evidence (Milestone 6.5) must also be
        re-pointed to the survivor as well."""
        if survivor_id == merged_id:
            raise InvalidMergeError()
        survivor = await self._node(user, survivor_id)
        merged = await self._node(user, merged_id)
        if survivor.workspace_id != merged.workspace_id:
            raise InvalidMergeError()
        uid = user.id

        merged_aliases = await self._g.alias_rows(uid, merged.id)
        moved_aliases = 0
        for row in merged_aliases:
            row.knowledge_node_id = survivor.id
            moved_aliases += 1
        await self._db.flush()
        if merged.normalised_name != survivor.normalised_name:
            owner = await self._k.alias_owner(uid, survivor.workspace_id, merged.normalised_name)
            if owner is None:
                self._k.add_alias(
                    user_id=uid,
                    workspace_id=survivor.workspace_id,
                    knowledge_node_id=survivor.id,
                    alias=merged.name,
                    normalised_alias=merged.normalised_name,
                )
                moved_aliases += 1

        evidence_moved = await self._g.move_node_evidence(uid, merged.id, survivor.id)
        # learner evidence and question/card links follow the surviving concept (spec 13)
        await LearnerEvidenceRepository(self._db).repoint_node(uid, merged.id, survivor.id)
        await MasteryService(self._db).recalculate(uid, [survivor.id])

        edges_moved = edges_dropped = 0
        for edge in await self._g.edges_of_node(uid, merged.id):
            src = survivor.id if edge.source_node_id == merged.id else edge.source_node_id
            tgt = survivor.id if edge.target_node_id == merged.id else edge.target_node_id
            if src == tgt:  # the two concepts were related to each other: now a self-loop
                await self._g.delete_edge(uid, edge.id)
                edges_dropped += 1
                continue
            src, tgt = _ordered(src, tgt, edge.relationship_type)
            existing = await self._k.find_edge(uid, src, tgt, edge.relationship_type)
            if existing is not None and existing.id != edge.id:
                await self._g.move_edge_evidence(uid, edge.id, existing.id)
                await self._g.delete_edge(uid, edge.id)
                edges_dropped += 1
            else:
                edge.source_node_id, edge.target_node_id = src, tgt
                edges_moved += 1
            await self._db.flush()

        if not survivor.description and merged.description:
            survivor.description = merged.description
        if not survivor.definition and merged.definition:
            survivor.definition = merged.definition
        if survivor.difficulty is None and merged.difficulty:
            survivor.difficulty = merged.difficulty

        self._g.add_merge_history(
            id=uuid.uuid4(),
            user_id=uid,
            workspace_id=survivor.workspace_id,
            surviving_node_id=survivor.id,
            merged_node_id=merged.id,
            merged_snapshot={
                "name": merged.name,
                "node_type": merged.node_type,
                "origin": merged.origin,
                "aliases_moved": moved_aliases,
                "evidence_moved": evidence_moved,
                "relationships_moved": edges_moved,
                "relationships_dropped": edges_dropped,
            },
        )
        await self._db.flush()
        await self._g.delete_node(uid, merged.id)
        await self._db.commit()
        await self._db.refresh(survivor)
        logger.info("knowledge_merged", survivor=str(survivor.id), merged=str(merged.id))
        return (await self._decorate(uid, [survivor]))[0]

    # duplicate review ────────────────────────────────────────────────────────

    async def list_candidates(
        self,
        user: User,
        *,
        workspace_id: uuid.UUID | None,
        status: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int]:
        rows, total = await self._g.list_candidates(
            user.id, workspace_id=workspace_id, status=status, limit=limit, offset=offset
        )
        ids = {c.node_a_id for c in rows} | {c.node_b_id for c in rows}
        nodes = await self._g.get_nodes(user.id, ids)
        decorated = {d["id"]: d for d in await self._decorate(user.id, nodes)}
        out = []
        for c in rows:
            a, b = decorated.get(c.node_a_id), decorated.get(c.node_b_id)
            if a is None or b is None:  # one side was archived: nothing to review now
                continue
            out.append(
                {
                    "id": c.id,
                    "workspace_id": c.workspace_id,
                    "status": c.status,
                    "signals": list(c.signals),
                    "node_a": a,
                    "node_b": b,
                    "created_at": c.created_at,
                }
            )
        return out, total

    async def resolve_candidate(
        self, user: User, candidate_id: uuid.UUID, action: str, survivor_id: uuid.UUID | None
    ) -> dict[str, Any]:
        cand = await self._g.get_candidate(user.id, candidate_id)
        if cand is None:
            raise CandidateNotFoundError()
        if cand.status != "open":
            raise InvalidCandidateActionError()
        pair = {cand.node_a_id, cand.node_b_id}
        if action == "merge":
            if survivor_id not in pair:
                raise InvalidCandidateActionError()
            merged_id = (pair - {survivor_id}).pop()
            await self.merge(user, survivor_id, merged_id)  # the candidate row goes with the node
            return {"status": "merged", "survivor_id": survivor_id}
        if action == "related":
            from app.modules.knowledge.graph_schemas import EdgeCreate

            try:
                await self.create_edge(
                    user,
                    EdgeCreate(
                        source_node_id=cand.node_a_id,
                        target_node_id=cand.node_b_id,
                        relationship_type="RELATED_TO",
                    ),
                )
            except DuplicateRelationshipError:
                pass  # already related: the decision still stands
            cand = await self._g.get_candidate(user.id, candidate_id)
            assert cand is not None
            cand.status = "related"
        elif action == "keep_separate":
            cand.status = "kept_separate"
        elif action == "ignore":
            cand.status = "ignored"
        else:
            raise InvalidCandidateActionError()
        await self._db.commit()
        return {"status": cand.status}


_NODE_FIELDS = (
    "id",
    "workspace_id",
    "subject_id",
    "chapter_id",
    "name",
    "description",
    "definition",
    "node_type",
    "difficulty",
    "origin",
    "edited_by_user",
    "confidence",
    "archived_at",
    "created_at",
    "updated_at",
)
