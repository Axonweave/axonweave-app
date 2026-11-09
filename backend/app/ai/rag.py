"""RAG helpers (D-75): reference block, escaping, follow-up query, citation validation.

Document text is untrusted. It is escaped so it cannot forge the markers, and the model's `[n]`
markers are never trusted: the backend keeps only numbers that map to a retrieved chunk. Nothing
here logs text.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from app.repositories.retrieval_repository import ChunkHit

INSUFFICIENT_REPLY = (
    "I could not find enough information about this in your selected documents, so I won't guess. "
    "Try rephrasing the question, widening the document scope, or switching the answer mode to "
    "allow general knowledge."
)
SHORT_QUESTION_CHARS = 40
SNIPPET_CHARS = 300
_MARKER = re.compile(r"\[(\d{1,3})\]")


def escape_markup(text: str) -> str:
    """Neutralise marker look-alikes inside document text, names and headings."""
    return text.replace("<<<", "‹‹‹").replace(">>>", "›››")


def _location(hit: ChunkHit) -> str:
    parts = []
    if hit.page_number:
        parts.append(f"page {hit.page_number}")
    if hit.slide_number:
        parts.append(f"slide {hit.slide_number}")
    if hit.section_heading:
        parts.append(f"section: {escape_markup(hit.section_heading)[:120]}")
    return ", ".join(parts)


def build_user_turn(question: str, sources: Sequence[ChunkHit]) -> str:
    blocks = []
    for n, hit in enumerate(sources, start=1):
        header = f"<<<SOURCE {n} | {escape_markup(hit.document_name)[:120]}"
        location = _location(hit)
        header += f" | {location}>>>" if location else ">>>"
        blocks.append(f"{header}\n{escape_markup(hit.content)}\n<<<END SOURCE>>>")
    return "REFERENCE MATERIAL\n\n" + "\n\n".join(blocks) + f"\n\nQUESTION\n{question}"


def build_query(question: str, previous_question: str | None) -> str:
    """Follow-ups: a short question is searched together with the previous user question."""
    if previous_question and len(question.strip()) < SHORT_QUESTION_CHARS:
        return f"{previous_question.strip()} {question.strip()}"[:1000]
    return question


def validate_citations(text: str, source_count: int) -> tuple[str, list[int]]:
    """Strip `[n]` markers that do not map to a retrieved source; return the ranks actually used."""
    used: list[int] = []

    def repl(match: re.Match[str]) -> str:
        n = int(match.group(1))
        if 1 <= n <= source_count:
            if n not in used:
                used.append(n)
            return match.group(0)
        return ""

    cleaned = _MARKER.sub(repl, text)
    cleaned = re.sub(r"[ \t]+([.,;:!?])", r"\1", cleaned)
    return re.sub(r"[ \t]{2,}", " ", cleaned), sorted(used)
