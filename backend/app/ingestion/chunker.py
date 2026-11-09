"""Structure-aware chunking with provenance (spec 9). Pure functions; no I/O, no logging.

Rules: a chunk never crosses a page or slide; a new heading starts a new chunk once the
current one has reasonable size; paragraphs and tables are kept whole when they fit; only an
oversize block is split, at sentence (then word) boundaries; overlap is carried only between
chunks of one section.
Sizes use the same conservative character estimate as the context manager (D-47).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from app.ingestion.extractors.base import Block

CHARS_PER_TOKEN = 3
MIN_CHUNK_CHARS = 20
MAX_BBOXES = 50
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])")


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / CHARS_PER_TOKEN) if text else 0


@dataclass(frozen=True)
class ChunkSettings:
    target_tokens: int = 400
    overlap_tokens: int = 60
    max_tokens: int = 600

    def __post_init__(self) -> None:
        if not (0 <= self.overlap_tokens < self.target_tokens <= self.max_tokens):
            raise ValueError("require 0 <= overlap < target <= max")


@dataclass
class ChunkDraft:
    text: str
    page: int | None
    slide: int | None
    heading: str | None
    bboxes: list[dict[str, object]] | None
    from_ocr: bool

    @property
    def token_count(self) -> int:
        return estimate_tokens(self.text)

    @property
    def char_count(self) -> int:
        return len(self.text)


def _split_words(text: str, max_chars: int) -> list[str]:
    out: list[str] = []
    current = ""
    for word in text.split():
        while len(word) > max_chars:  # a single enormous token (e.g. base64): cut it
            if current:
                out.append(current)
                current = ""
            out.append(word[:max_chars])
            word = word[max_chars:]
        if current and len(current) + 1 + len(word) > max_chars:
            out.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        out.append(current)
    return out


def _pieces(block: Block, target_tokens: int) -> list[str]:
    """The block as one piece, or several when it is larger than a target-sized chunk."""
    text = block.text
    target_chars = target_tokens * CHARS_PER_TOKEN
    if len(text) <= target_chars:
        return [text]
    if block.kind == "table":
        units = text.split("\n")
    else:
        units = [s for part in text.split("\n\n") for s in _SENTENCE.split(part) if s.strip()]
    pieces: list[str] = []
    current = ""
    for unit in units:
        for fragment in _split_words(unit, target_chars) if len(unit) > target_chars else [unit]:
            sep = "\n" if block.kind == "table" else " "
            if current and len(current) + len(sep) + len(fragment) > target_chars:
                pieces.append(current)
                current = fragment
            else:
                current = f"{current}{sep}{fragment}" if current else fragment
    if current:
        pieces.append(current)
    return pieces


def _tail_for_overlap(text: str, overlap_tokens: int) -> str:
    """The last whole sentences of `text` that fit in the overlap budget."""
    if overlap_tokens <= 0:
        return ""
    budget = overlap_tokens * CHARS_PER_TOKEN
    sentences = [s for s in _SENTENCE.split(text) if s.strip()]
    tail = ""
    for sentence in reversed(sentences):
        if len(tail) + len(sentence) + 1 > budget:
            break
        tail = f"{sentence} {tail}".strip()
    return tail


class _Buffer:
    def __init__(self) -> None:
        self.parts: list[str] = []
        self.page: int | None = None
        self.slide: int | None = None
        self.heading: str | None = None
        self.bboxes: list[dict[str, object]] = []
        self.ocr_flags: list[bool] = []

    @property
    def text(self) -> str:
        return "\n\n".join(self.parts)

    @property
    def tokens(self) -> int:
        return estimate_tokens(self.text)

    def empty(self) -> bool:
        return not self.parts

    def add(self, piece: str, block: Block, *, with_bbox: bool) -> None:
        if self.empty():
            self.page, self.slide = block.page, block.slide
            self.heading = block.heading
        self.parts.append(piece)
        self.ocr_flags.append(block.from_ocr)
        if with_bbox and block.bbox is not None and block.page is not None:
            if len(self.bboxes) < MAX_BBOXES:
                self.bboxes.append({"page": block.page, "bbox": list(block.bbox)})

    def to_draft(self) -> ChunkDraft:
        return ChunkDraft(
            text=self.text,
            page=self.page,
            slide=self.slide,
            heading=self.heading,
            bboxes=self.bboxes or None,
            from_ocr=bool(self.ocr_flags) and all(self.ocr_flags),
        )


def chunk_blocks(blocks: list[Block], settings: ChunkSettings | None = None) -> list[ChunkDraft]:
    cfg = settings or ChunkSettings()
    drafts: list[ChunkDraft] = []
    buf = _Buffer()

    def flush(*, carry_overlap: bool) -> None:
        nonlocal buf
        if buf.empty():
            return
        draft = buf.to_draft()
        drafts.append(draft)
        fresh = _Buffer()
        if carry_overlap:
            tail = _tail_for_overlap(draft.text, cfg.overlap_tokens)
            if tail:
                fresh.parts.append(tail)
                fresh.page, fresh.slide, fresh.heading = draft.page, draft.slide, draft.heading
                fresh.ocr_flags.append(draft.from_ocr)
        buf = fresh

    last_unit: tuple[int | None, int | None] | None = None
    overlap_only = False  # buffer holds nothing but carried overlap
    for block in blocks:
        # A chunk never crosses a page or a slide, so its page/slide label is exact for citations.
        unit = (block.page, block.slide)
        if unit != last_unit and (block.page is not None or block.slide is not None):
            if not overlap_only:
                flush(carry_overlap=False)
            buf = _Buffer()
            last_unit = unit
            overlap_only = False
        if block.kind == "heading" and not buf.empty() and not overlap_only:
            if buf.tokens >= cfg.target_tokens // 4:
                flush(carry_overlap=False)
        for piece in _pieces(block, cfg.target_tokens):
            if (
                not buf.empty()
                and buf.tokens + estimate_tokens(piece) > cfg.target_tokens
                and not overlap_only
            ):
                flush(carry_overlap=block.kind != "heading")
                overlap_only = not buf.empty()
            elif overlap_only and buf.tokens + estimate_tokens(piece) > cfg.max_tokens:
                buf = _Buffer()  # carried overlap plus this piece would be too big: drop overlap
            if buf.empty():
                buf.heading = block.heading
            buf.add(piece, block, with_bbox=True)
            overlap_only = False
            if buf.tokens > cfg.max_tokens:  # defensive: pieces are <= target, so this is rare
                flush(carry_overlap=False)
    if not buf.empty() and not overlap_only:
        drafts.append(buf.to_draft())
    return [d for d in drafts if len(d.text.strip()) >= MIN_CHUNK_CHARS or len(drafts) == 1]
