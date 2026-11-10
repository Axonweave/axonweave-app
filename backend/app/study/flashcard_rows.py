"""Turn validated generator output into `flashcards` rows (shared by the engine and the service)."""

from __future__ import annotations

from typing import Any


def card_references(refs: list[int], sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Source numbers -> stored references (ids and locations only, never text; D-82)."""
    by_rank = {int(s["rank"]): s for s in sources}
    out: list[dict[str, Any]] = []
    for ref in refs:
        src = by_rank.get(ref)
        if src is None:
            continue
        out.append(
            {
                k: src[k]
                for k in ("rank", "kind", "document_id", "chunk_id", "page_number", "slide_number")
                if k in src
            }
        )
    return out


def generated_card_rows(cards: list[Any], sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "front": c.front,
            "back": c.back,
            "explanation": c.explanation or None,
            "card_type": c.card_type,
            "difficulty": c.difficulty,
            "source_references": card_references(c.source_refs, sources),
            "origin": "generated",
        }
        for c in cards
    ]
