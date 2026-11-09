"""DOCX and PPTX extraction (worker only). Macros are never run and links are never followed."""

from __future__ import annotations

import io
from typing import Any

from app.ingestion.extractors.base import (
    FILE_CORRUPT,
    TOO_MANY_PAGES,
    WARN_IMAGES_IGNORED,
    WARN_TEXT_TRUNCATED,
    Block,
    CharBudget,
    Extraction,
    ExtractionError,
    ExtractionLimits,
)


def _table_text(rows: list[list[str]]) -> str:
    return "\n".join(" | ".join(cell.strip() for cell in row) for row in rows if any(row))


def extract_docx(data: bytes, limits: ExtractionLimits) -> Extraction:
    try:
        import docx
        from docx.table import Table
        from docx.text.paragraph import Paragraph

        document = docx.Document(io.BytesIO(data))
        body = document.element.body
    except Exception:
        raise ExtractionError(FILE_CORRUPT) from None
    result = Extraction(blocks=[], method="python-docx")
    budget = CharBudget(limits.max_chars)
    try:
        for child in body.iterchildren():
            if budget.exceeded:
                break
            tag = child.tag.rsplit("}", 1)[-1]
            if tag == "p":
                para = Paragraph(child, document)
                text = para.text.strip()
                if not text:
                    continue
                style = (para.style.name if para.style is not None else "") or ""
                kind, level = "paragraph", 0
                if style.lower().startswith("heading") or style == "Title":
                    kind = "heading"
                    digits = "".join(ch for ch in style if ch.isdigit())
                    level = int(digits) if digits else 1
                elif "list" in style.lower():
                    kind = "list"
                kept = budget.take(text)
                if kept:
                    result.blocks.append(Block(text=kept, kind=kind, level=level))
            elif tag == "tbl":
                table = Table(child, document)
                rows = [[cell.text for cell in row.cells] for row in table.rows]
                text = _table_text(rows)
                kept = budget.take(text) if text.strip() else None
                if kept:
                    result.blocks.append(Block(text=kept, kind="table"))
        if document.inline_shapes and len(document.inline_shapes):
            result.add_warning(WARN_IMAGES_IGNORED)
    except ExtractionError:
        raise
    except Exception:
        raise ExtractionError(FILE_CORRUPT) from None
    if budget.exceeded:
        result.add_warning(WARN_TEXT_TRUNCATED)
    return result


def _shape_blocks(shape: Any, slide_no: int, out: list[Block], seen_pictures: list[int]) -> None:
    """Collect text from one shape, recursing into groups."""
    if getattr(shape, "shape_type", None) == 6:  # MSO_SHAPE_TYPE.GROUP
        for inner in shape.shapes:
            _shape_blocks(inner, slide_no, out, seen_pictures)
        return
    if getattr(shape, "shape_type", None) == 13:  # PICTURE
        seen_pictures.append(1)
        return
    if getattr(shape, "has_table", False) and shape.has_table:
        rows = [[cell.text for cell in row.cells] for row in shape.table.rows]
        text = _table_text(rows)
        if text.strip():
            out.append(Block(text=text, slide=slide_no, kind="table"))
        return
    if getattr(shape, "has_text_frame", False) and shape.has_text_frame:
        text = "\n".join(p.text for p in shape.text_frame.paragraphs).strip()
        if text:
            out.append(Block(text=text, slide=slide_no))


def extract_pptx(data: bytes, limits: ExtractionLimits) -> Extraction:
    try:
        from pptx import Presentation

        prs = Presentation(io.BytesIO(data))
        slides = list(prs.slides)
    except Exception:
        raise ExtractionError(FILE_CORRUPT) from None
    if len(slides) > limits.max_pages:
        raise ExtractionError(TOO_MANY_PAGES, "The presentation has too many slides.")
    result = Extraction(blocks=[], method="python-pptx", slide_count=len(slides))
    budget = CharBudget(limits.max_chars)
    pictures: list[int] = []
    try:
        for number, slide in enumerate(slides, start=1):
            if budget.exceeded:
                break
            title_shape = slide.shapes.title
            title = title_shape.text_frame.text.strip() if title_shape is not None else ""
            slide_blocks: list[Block] = []
            if title:
                slide_blocks.append(Block(text=title, slide=number, kind="heading", level=1))
            for shape in slide.shapes:
                if title_shape is not None and shape.shape_id == title_shape.shape_id:
                    continue
                _shape_blocks(shape, number, slide_blocks, pictures)
            if slide.has_notes_slide:
                notes = slide.notes_slide.notes_text_frame
                note_text = notes.text.strip() if notes is not None else ""
                if note_text:
                    slide_blocks.append(Block(text=note_text, slide=number, kind="notes"))
            for block in slide_blocks:
                kept = budget.take(block.text)
                if kept is None:
                    break
                block.text = kept
                result.blocks.append(block)
    except ExtractionError:
        raise
    except Exception:
        raise ExtractionError(FILE_CORRUPT) from None
    if pictures:
        result.add_warning(WARN_IMAGES_IGNORED)
    if budget.exceeded:
        result.add_warning(WARN_TEXT_TRUNCATED)
    return result
