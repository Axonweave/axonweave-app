"""Plain text, Markdown and image extraction (worker only)."""

from __future__ import annotations

import io
import re

from app.ingestion.extractors.base import (
    FILE_CORRUPT,
    LOW_OCR_CONFIDENCE,
    NO_TEXT_FOUND,
    OCR_UNAVAILABLE,
    WARN_LOW_OCR_CONFIDENCE,
    WARN_OCR_USED,
    WARN_TEXT_TRUNCATED,
    Block,
    CharBudget,
    Extraction,
    ExtractionError,
    ExtractionLimits,
)
from app.ingestion.extractors.ocr import ocr_available, ocr_image

_MD_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")


def extract_text(data: bytes, limits: ExtractionLimits, *, markdown: bool) -> Extraction:
    """Split into paragraphs on blank lines; Markdown headings become heading blocks. Code fences
    stay in one block so code is not cut in the middle."""
    text = data.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
    result = Extraction(blocks=[], method="markdown" if markdown else "text")
    budget = CharBudget(limits.max_chars)
    paragraph: list[str] = []
    in_fence = False

    def flush() -> None:
        if not paragraph:
            return
        body = "\n".join(paragraph).strip()
        paragraph.clear()
        kept = budget.take(body) if body else None
        if kept:
            result.blocks.append(Block(text=kept))

    for line in text.split("\n"):
        if budget.exceeded:
            break
        if markdown and _FENCE.match(line):
            in_fence = not in_fence
            paragraph.append(line)
            continue
        if in_fence:
            paragraph.append(line)
            continue
        heading = _MD_HEADING.match(line) if markdown else None
        if heading:
            flush()
            kept = budget.take(heading.group(2).strip())
            if kept:
                result.blocks.append(Block(text=kept, kind="heading", level=len(heading.group(1))))
        elif not line.strip():
            flush()
        else:
            paragraph.append(line)
    flush()
    if budget.exceeded:
        result.add_warning(WARN_TEXT_TRUNCATED)
    return result


def extract_image(data: bytes, limits: ExtractionLimits) -> Extraction:
    from PIL import Image

    if not limits.ocr_enabled or not ocr_available():
        raise ExtractionError(OCR_UNAVAILABLE, "OCR is not available for image documents.")
    Image.MAX_IMAGE_PIXELS = limits.image_max_pixels
    try:
        opened = Image.open(io.BytesIO(data))
        opened.load()
        image = opened.convert("RGB")
    except Exception:  # corrupt, truncated or a decompression bomb
        raise ExtractionError(FILE_CORRUPT) from None
    text, confidences = ocr_image(image, limits)
    if not text.strip():
        raise ExtractionError(NO_TEXT_FOUND, "No text was found in the image.")
    result = Extraction(blocks=[], method="ocr", ocr_used=True, ocr_confidences=confidences)
    budget = CharBudget(limits.max_chars)
    for part in re.split(r"\n\s*\n", text):
        kept = budget.take(part.strip())
        if kept:
            result.blocks.append(Block(text=kept, from_ocr=True))
    result.add_warning(WARN_OCR_USED)
    mean = result.ocr_mean_confidence
    if mean is not None and mean < LOW_OCR_CONFIDENCE:
        result.add_warning(WARN_LOW_OCR_CONFIDENCE)
    if budget.exceeded:
        result.add_warning(WARN_TEXT_TRUNCATED)
    return result
