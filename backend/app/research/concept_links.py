"""Matching analysed papers to existing knowledge nodes (Phase 7 M7.10, spec 32.2). Pure functions.

A paper is linked to a node when one of the paper's verified claims names the node (its name or one
of its aliases) as a whole phrase. Nothing is created in the graph and no model is called: this
only connects research to concepts that already exist, so no duplicate concept can come from it.
Reading a paper is not evidence of mastery; these links never reach the learner tables.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from app.research.claims import LoadedPaper, StoredClaim

MIN_NAME_CHARS = 3
_WORDS = re.compile(r"[^\W_]+", re.UNICODE)


def normalise(text: str) -> str:
    return " ".join(_WORDS.findall(text.casefold()))


@dataclass(frozen=True)
class NodeNames:
    node_id: uuid.UUID
    name: str
    aliases: tuple[str, ...] = ()


@dataclass
class ConceptMention:
    paper_id: uuid.UUID
    node_id: uuid.UUID
    match_kind: str  # name | alias
    matched_text: str
    claim: StoredClaim
    mention_count: int
    extraction_id: uuid.UUID


def find_mentions(papers: list[LoadedPaper], nodes: list[NodeNames]) -> list[ConceptMention]:
    """One mention per (paper, node): the first verified claim that names the node (preferring a
    claim with a quotation), how many claims name it and whether the name or an alias matched."""
    needles: list[tuple[NodeNames, str, str, str]] = []  # node, kind, shown, normalised
    for node in nodes:
        for kind, raw in (("name", node.name), *(("alias", a) for a in node.aliases)):
            norm = normalise(raw)
            if len(norm) >= MIN_NAME_CHARS:
                needles.append((node, kind, raw, norm))
    out: list[ConceptMention] = []
    for paper in papers:
        texts = [(c, f" {normalise(c.text)} ") for c in paper.claims if c.section != "references"]
        found: dict[uuid.UUID, ConceptMention] = {}
        for node, kind, raw, norm in needles:
            probe = f" {norm} "
            hits = [c for c, padded in texts if probe in padded]
            if not hits:
                continue
            first = next((c for c in hits if c.evidence_id), hits[0])
            current = found.get(node.node_id)
            if current is None or (current.match_kind == "alias" and kind == "name"):
                found[node.node_id] = ConceptMention(
                    paper.paper_id,
                    node.node_id,
                    kind,
                    raw[:200],
                    first,
                    len(hits),
                    paper.extraction_id,
                )
            elif current.match_kind == kind:
                current.mention_count = max(current.mention_count, len(hits))
        out.extend(found.values())
    return out
