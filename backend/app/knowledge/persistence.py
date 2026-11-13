"""Turns verified extraction output into graph rows (spec 9.6, 9.7; D-126).

Idempotent: running the same extraction twice (a retry, a re-run) adds nothing new. Matching is
deterministic (normalised name, alias); embeddings are never used to merge. Possible duplicates
become reviewable candidates. A node the user edited is never overwritten; re-extraction only adds
evidence to it. Runs inside the caller's transaction."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.normalise import normalise_name
from app.knowledge.validation import VerifiedConcept, VerifiedEvidence, VerifiedOutput
from app.models.knowledge import SYMMETRIC_TYPES, KnowledgeNode
from app.repositories.knowledge_repository import KnowledgeRepository


@dataclass
class Placement:
    user_id: uuid.UUID
    workspace_id: uuid.UUID
    subject_id: uuid.UUID | None
    chapter_id: uuid.UUID | None
    document_id: uuid.UUID
    document_version_id: uuid.UUID
    job_id: uuid.UUID


@dataclass
class PersistStats:
    nodes_created: int = 0
    nodes_matched: int = 0
    edges_created: int = 0
    edges_matched: int = 0
    evidence_added: int = 0
    candidates_added: int = 0
    aliases_added: int = 0
    stale_marked: int = 0
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "nodes_created": self.nodes_created,
            "nodes_matched": self.nodes_matched,
            "edges_created": self.edges_created,
            "edges_matched": self.edges_matched,
            "evidence_added": self.evidence_added,
            "aliases_added": self.aliases_added,
            "duplicate_candidates": self.candidates_added,
            "stale_evidence_marked": self.stale_marked,
        }


def _evidence_rows(
    where: Placement,
    evidence: list[VerifiedEvidence],
    *,
    node_id: uuid.UUID | None,
    edge_id: uuid.UUID | None,
    kinds: list[str],
    confidence: float,
) -> list[dict[str, Any]]:
    rows = []
    for ev, kind in zip(evidence, kinds, strict=True):
        rows.append(
            {
                "id": uuid.uuid4(),
                "user_id": where.user_id,
                "workspace_id": where.workspace_id,
                "knowledge_node_id": node_id,
                "knowledge_edge_id": edge_id,
                "document_id": where.document_id,
                "document_version_id": where.document_version_id,
                "chunk_index": ev.unit.chunk_index,
                "chunk_id": ev.unit.chunk_id,
                "page_number": ev.unit.page_number,
                "slide_number": ev.unit.slide_number,
                "quote": ev.quote,
                "quote_hash": ev.quote_hash,
                "evidence_type": kind,
                "extraction_method": "llm",
                "extraction_job_id": where.job_id,
                "confidence": Decimal(str(round(confidence, 3))),
                "stale": False,
            }
        )
    return rows


async def persist_graph(db: AsyncSession, where: Placement, result: VerifiedOutput) -> PersistStats:
    repo = KnowledgeRepository(db)
    stats = PersistStats()
    node_ids: dict[str, uuid.UUID] = {}

    for concept in result.concepts:
        node, created = await _resolve_node(db, repo, where, concept, stats)
        node_ids[concept.normalised_name] = node.id
        stats.nodes_created += int(created)
        stats.nodes_matched += int(not created)
        await _add_aliases(repo, where, node, concept, stats)
        kinds = [
            "definition" if (i == 0 and concept.definition) else "mention"
            for i in range(len(concept.evidence))
        ]
        stats.evidence_added += await repo.add_evidence(
            _evidence_rows(
                where,
                concept.evidence,
                node_id=node.id,
                edge_id=None,
                kinds=kinds,
                confidence=concept.confidence,
            )
        )

    for rel in result.relationships:
        source_id = node_ids.get(rel.source)
        target_id = node_ids.get(rel.target)
        if source_id is None or target_id is None or source_id == target_id:
            continue
        if rel.relationship_type in SYMMETRIC_TYPES and str(target_id) < str(source_id):
            source_id, target_id = target_id, source_id  # stored once, smaller id first
        edge = await repo.find_edge(where.user_id, source_id, target_id, rel.relationship_type)
        created = False
        if edge is None:
            try:
                async with db.begin_nested():
                    edge = repo.add_edge(
                        user_id=where.user_id,
                        workspace_id=where.workspace_id,
                        source_node_id=source_id,
                        target_node_id=target_id,
                        relationship_type=rel.relationship_type,
                        description=rel.description,
                        confidence=Decimal(str(round(rel.confidence, 3))),
                        statement_kind=rel.statement_kind,
                        origin="extracted",
                    )
                    await db.flush()
                created = True
            except IntegrityError:  # a concurrent run created it first
                edge = await repo.find_edge(
                    where.user_id, source_id, target_id, rel.relationship_type
                )
                if edge is None:
                    raise
        elif not edge.description and rel.description and edge.origin == "extracted":
            edge.description = rel.description
        stats.edges_created += int(created)
        stats.edges_matched += int(not created)
        stats.evidence_added += await repo.add_evidence(
            _evidence_rows(
                where,
                rel.evidence,
                node_id=None,
                edge_id=edge.id,
                kinds=["relationship_statement"] * len(rel.evidence),
                confidence=rel.confidence,
            )
        )

    stats.stale_marked = await repo.mark_stale(
        where.user_id, where.document_id, where.document_version_id
    )
    return stats


async def _resolve_node(
    db: AsyncSession,
    repo: KnowledgeRepository,
    where: Placement,
    concept: VerifiedConcept,
    stats: PersistStats,
) -> tuple[KnowledgeNode, bool]:
    """Exact (name, type) match, else an alias match, else a new node."""
    existing = await repo.find_node(
        where.user_id, where.workspace_id, concept.normalised_name, concept.node_type
    )
    if existing is None:
        existing = await repo.node_by_alias(
            where.user_id, where.workspace_id, concept.normalised_name
        )
    if existing is not None:
        _fill_blanks(existing, concept)
        return existing, False

    try:
        async with db.begin_nested():
            node = repo.add_node(
                user_id=where.user_id,
                workspace_id=where.workspace_id,
                subject_id=where.subject_id,
                chapter_id=where.chapter_id,
                name=concept.name,
                normalised_name=concept.normalised_name,
                description=concept.description,
                definition=concept.definition,
                node_type=concept.node_type,
                difficulty=concept.difficulty,
                attributes={},
                origin="extracted",
                edited_by_user=False,
                confidence=Decimal(str(round(concept.confidence, 3))),
            )
            await db.flush()
    except IntegrityError:  # a concurrent run created the same node first
        found = await repo.find_node(
            where.user_id, where.workspace_id, concept.normalised_name, concept.node_type
        )
        if found is None:
            raise
        return found, False

    # Same name under another type is a likely duplicate: record it for review, do not merge.
    for other in await repo.nodes_named(where.user_id, where.workspace_id, concept.normalised_name):
        if other.id != node.id and await repo.add_candidate(
            where.user_id, where.workspace_id, node.id, other.id, "same_name_different_type"
        ):
            stats.candidates_added += 1
    return node, True


def _fill_blanks(node: KnowledgeNode, concept: VerifiedConcept) -> None:
    """Never overwrite: only fill a missing field, and never touch a node the user edited."""
    if node.edited_by_user or node.origin == "user":
        return
    if not node.description and concept.description:
        node.description = concept.description
    if not node.definition and concept.definition:
        node.definition = concept.definition
    if node.difficulty is None and concept.difficulty:
        node.difficulty = concept.difficulty


async def _add_aliases(
    repo: KnowledgeRepository,
    where: Placement,
    node: KnowledgeNode,
    concept: VerifiedConcept,
    stats: PersistStats,
) -> None:
    if node.edited_by_user:
        return  # the user owns this node's naming
    known = await repo.aliases_of(where.user_id, node.id)
    for alias in concept.aliases:
        key = normalise_name(alias)
        if not key or key == node.normalised_name or key in known:
            continue
        owner = await repo.alias_owner(where.user_id, where.workspace_id, key)
        if owner is not None and owner != node.id:
            if await repo.add_candidate(
                where.user_id, where.workspace_id, node.id, owner, "alias_shared"
            ):
                stats.candidates_added += 1
            continue
        clash = [
            n
            for n in await repo.nodes_named(where.user_id, where.workspace_id, key)
            if n.id != node.id
        ]
        if clash:  # the alias is another concept's own name: review, do not attach
            if await repo.add_candidate(
                where.user_id, where.workspace_id, node.id, clash[0].id, "alias_matches_name"
            ):
                stats.candidates_added += 1
            continue
        repo.add_alias(
            user_id=where.user_id,
            workspace_id=where.workspace_id,
            knowledge_node_id=node.id,
            alias=alias,
            normalised_alias=key,
        )
        known.add(key)
        stats.aliases_added += 1
