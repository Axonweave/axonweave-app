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


def build_user_turn(units: Sequence[SourceUnit], instruction: str, start: int = 1) -> str:
    """`start` is the number of the first unit, so batches of one long scope keep global numbers."""
    blocks = []
    for n, unit in enumerate(units, start=start):
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


def build_notes_turn(notes: Sequence[tuple[str, Sequence[int]]], instruction: str) -> str:
    """Working notes (model output derived from untrusted text) for a reduce or condense step.
    Each note keeps the source numbers it came from; text is escaped like any other source text."""
    nl = "\n"
    blocks = []
    for k, (text, refs) in enumerate(notes, start=1):
        label = ", ".join(str(r) for r in refs) or "none"
        blocks.append(
            f"<<<NOTE {k} | sources {label}>>>{nl}{escape_markup(text)}{nl}<<<END NOTE>>>"
        )
    body = (nl * 2).join(blocks)
    head = "REFERENCE MATERIAL (working notes, in reading order)"
    return f"{head}{nl * 2}{body}{nl * 2}{instruction}"
