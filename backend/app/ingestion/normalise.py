"""Text normalisation and structure detection (spec 8). Pure functions; no I/O, no logging."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter

from app.ingestion.extractors.base import Block

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SPACES = re.compile(r"[ \t  -​  　]+")
_HYPHEN_BREAK = re.compile(r"(?<=[a-z])-\n(?=[a-z])")
_MANY_NEWLINES = re.compile(r"\n{3,}")
_LIGATURES = str.maketrans({"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl"})


def normalise_text(text: str) -> str:
    """NFC, no control characters, collapsed spaces, rejoined hyphenated line breaks."""
    text = unicodedata.normalize("NFC", text).translate(_LIGATURES)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL.sub("", text)
    text = _HYPHEN_BREAK.sub("", text)
    text = _SPACES.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    return _MANY_NEWLINES.sub("\n\n", text).strip()


_PAGE_NUMBER = re.compile(r"(page\s*)?\d+(\s*(/|of)\s*\d+)?", re.IGNORECASE)


def _furniture_key(text: str) -> str:
    """Page numbers differ on every page, so they share one key; other text must match exactly."""
    lowered = text.strip().lower()
    return "#page-number#" if _PAGE_NUMBER.fullmatch(lowered) else lowered


def _drop_repeated_page_furniture(blocks: list[Block], page_count: int | None) -> list[Block]:
    """Remove short blocks (running headers, footers, page numbers) repeated on many pages."""
    if not page_count or page_count < 4:
        return blocks
    seen: dict[str, set[int]] = {}
    for b in blocks:
        if b.page is not None and len(b.text) <= 100:
            seen.setdefault(_furniture_key(b.text), set()).add(b.page)
    repeated = {k for k, pages in seen.items() if len(pages) >= max(3, page_count // 2)}
    if not repeated:
        return blocks
    return [
        b
        for b in blocks
        if not (b.page is not None and len(b.text) <= 100 and _furniture_key(b.text) in repeated)
    ]


def normalise_blocks(blocks: list[Block], page_count: int | None = None) -> list[Block]:
    """Normalise every block, drop empties and page furniture, and fill in each block's section
    heading. A new slide always starts with no heading of its own until its title is seen."""
    cleaned: list[Block] = []
    for b in blocks:
        text = normalise_text(b.text)
        if text:
            b.text = text
            cleaned.append(b)
    cleaned = _drop_repeated_page_furniture(cleaned, page_count)

    current: str | None = None
    last_slide: int | None = None
    for b in cleaned:
        if b.slide is not None and b.slide != last_slide:
            current = None
            last_slide = b.slide
        if b.kind == "heading":
            current = b.text.split("\n")[0][:300]
        b.heading = current
    return cleaned


def word_count(blocks: list[Block]) -> int:
    return sum(len(b.text.split()) for b in blocks)


def block_kind_counts(blocks: list[Block]) -> Counter[str]:
    return Counter(b.kind for b in blocks)
