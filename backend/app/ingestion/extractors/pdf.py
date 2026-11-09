"""PDF extraction with PyMuPDF (worker only). OCR is used only for pages without digital text."""

from __future__ import annotations

import statistics
from typing import Any

from app.ingestion.extractors.base import (
    FILE_CORRUPT,
    FILE_ENCRYPTED,
    LOW_OCR_CONFIDENCE,
    TOO_MANY_PAGES,
    WARN_LOW_OCR_CONFIDENCE,
    WARN_OCR_SKIPPED,
    WARN_OCR_USED,
    WARN_PAGES_WITHOUT_TEXT,
    WARN_TEXT_TRUNCATED,
    Block,
    CharBudget,
    Extraction,
    ExtractionError,
    ExtractionLimits,
)
from app.ingestion.extractors.ocr import ocr_available, ocr_image

_MIN_TEXT_CHARS = 20  # a page with fewer characters than this has no usable text layer
_HEADING_RATIO = 1.15  # span size relative to the body size that marks a heading


def extract_pdf(data: bytes, limits: ExtractionLimits) -> Extraction:
    import pymupdf

    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception:
        raise ExtractionError(FILE_CORRUPT) from None
    try:
        if doc.needs_pass or doc.is_encrypted:
            raise ExtractionError(FILE_ENCRYPTED, "Password-protected documents are not supported.")
        page_count = doc.page_count
        if page_count == 0:
            raise ExtractionError(FILE_CORRUPT)
        if page_count > limits.max_pages:
            raise ExtractionError(TOO_MANY_PAGES, "The document has too many pages.")
        result = Extraction(blocks=[], method="pymupdf", page_count=page_count)
        budget = CharBudget(limits.max_chars)

        pages: list[list[dict[str, Any]]] = []
        sizes: list[tuple[float, int]] = []
        try:
            for index in range(page_count):
                raw = doc[index].get_text("dict")["blocks"]
                text_blocks = [b for b in raw if b.get("type") == 0]
                for b in text_blocks:
                    for line in b.get("lines", []):
                        for span in line.get("spans", []):
                            sizes.append((float(span.get("size", 0)), len(span.get("text", ""))))
                pages.append(text_blocks)
        except Exception:
            raise ExtractionError(FILE_CORRUPT) from None
        body_size = _weighted_median(sizes)

        pages_without_text = 0
        for number, text_blocks in enumerate(pages, start=1):
            if budget.exceeded:
                break
            page_chars = 0
            page_blocks: list[Block] = []
            for b in sorted(text_blocks, key=lambda b: (round(b["bbox"][1]), b["bbox"][0])):
                text = _block_text(b)
                if not text.strip():
                    continue
                page_chars += len(text.strip())
                size = _block_size(b)
                is_heading = (
                    body_size > 0
                    and size >= body_size * _HEADING_RATIO
                    and len(text) <= 160
                    and len(b.get("lines", [])) <= 3
                )
                page_blocks.append(
                    Block(
                        text=text,
                        page=number,
                        kind="heading" if is_heading else "paragraph",
                        level=_heading_level(size, body_size) if is_heading else 0,
                        bbox=_bbox(b["bbox"]),
                    )
                )
            if page_chars < _MIN_TEXT_CHARS:
                pages_without_text += 1
                page_blocks = _ocr_page(doc[index_of(number)], number, limits, result)
            for block in page_blocks:
                kept = budget.take(block.text)
                if kept is None:
                    break
                block.text = kept
                result.blocks.append(block)
        if budget.exceeded:
            result.add_warning(WARN_TEXT_TRUNCATED)
        if pages_without_text and not result.ocr_used:
            result.add_warning(WARN_PAGES_WITHOUT_TEXT)
        if result.ocr_used:
            result.add_warning(WARN_OCR_USED)
            mean = result.ocr_mean_confidence
            if mean is not None and mean < LOW_OCR_CONFIDENCE:
                result.add_warning(WARN_LOW_OCR_CONFIDENCE)
        return result
    finally:
        doc.close()


def index_of(page_number: int) -> int:
    return page_number - 1


def _ocr_page(page: Any, number: int, limits: ExtractionLimits, result: Extraction) -> list[Block]:
    """OCR one page that has no text layer. Skipped (with a warning) when OCR is off."""
    if not limits.ocr_enabled or not ocr_available():
        result.add_warning(WARN_OCR_SKIPPED)
        return []
    from PIL import Image

    pixmap = page.get_pixmap(dpi=limits.ocr_dpi)
    if pixmap.width * pixmap.height > limits.image_max_pixels:
        result.add_warning(WARN_OCR_SKIPPED)
        return []
    image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    text, confidences = ocr_image(image, limits)
    if not text.strip():
        return []
    result.ocr_used = True
    result.ocr_confidences.extend(confidences)
    return [
        Block(text=part.strip(), page=number, from_ocr=True)
        for part in text.split("\n\n")
        if part.strip()
    ] or [Block(text=text.strip(), page=number, from_ocr=True)]


def _block_text(block: dict[str, Any]) -> str:
    lines = []
    for line in block.get("lines", []):
        lines.append("".join(span.get("text", "") for span in line.get("spans", [])))
    return "\n".join(lines).strip()


def _block_size(block: dict[str, Any]) -> float:
    sizes = [
        float(span.get("size", 0))
        for line in block.get("lines", [])
        for span in line.get("spans", [])
    ]
    return max(sizes) if sizes else 0.0


def _weighted_median(sizes: list[tuple[float, int]]) -> float:
    expanded = [round(size, 1) for size, chars in sizes for _ in range(min(chars, 50)) if size > 0]
    return float(statistics.median(expanded)) if expanded else 0.0


def _heading_level(size: float, body: float) -> int:
    ratio = size / body if body else 1.0
    return 1 if ratio >= 1.6 else 2 if ratio >= 1.3 else 3


def _bbox(raw: Any) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = (round(float(v), 1) for v in raw)
    return (x0, y0, x1, y1)
