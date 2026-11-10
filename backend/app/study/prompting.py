"""Builds the user turn: SOURCE blocks followed by the generator's TASK block (D-80).

Document text is untrusted: it is escaped so it cannot forge the markers (same helper Phase 3 uses),
and the model's `[n]` / `source_refs` are never trusted (the engine maps them to the units it sent).
Nothing here logs text.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.ai.rag import escape_markup
from app.study.source_reader import SourceUnit


def _location(unit: SourceUnit) -> str:
    parts = []
    if unit.page_number:
        parts.append(f"page {unit.page_number}")
    if unit.slide_number:
        parts.append(f"slide {unit.slide_number}")
    if unit.section_heading:
        parts.append(f"section: {escape_markup(unit.section_heading)[:120]}")
    return ", ".join(parts)


def build_user_turn(units: Sequence[SourceUnit], instruction: str) -> str:
    blocks = []
    for n, unit in enumerate(units, start=1):
        header = f"<<<SOURCE {n} | {escape_markup(unit.document_name)[:120]}"
        location = _location(unit)
        header += f" | {location}>>>" if location else ">>>"
        blocks.append(f"{header}\n{escape_markup(unit.content)}\n<<<END SOURCE>>>")
    return "REFERENCE MATERIAL\n\n" + "\n\n".join(blocks) + "\n\n" + instruction


def correction_turn(problem: str) -> str:
    """The one correction request. `problem` is field paths and rule names only."""
    return (
        "Your previous reply could not be used. Problems: "
        f"{problem}. Reply again with ONE corrected JSON object that follows the schema in the "
        "TASK block exactly, and nothing else."
    )


def source_refs_for(units: Sequence[SourceUnit]) -> list[dict[str, object]]:
    """Provenance for the stored material: ids and locations, never text (D-82)."""
    refs: list[dict[str, object]] = []
    for n, unit in enumerate(units, start=1):
        ref: dict[str, object] = {"rank": n}
        if unit.chunk_id is None:
            ref["kind"] = "text"
        else:
            ref.update(
                kind="chunk",
                document_id=str(unit.document_id),
                chunk_id=str(unit.chunk_id),
                page_number=unit.page_number,
                slide_number=unit.slide_number,
            )
        refs.append(ref)
    return refs
