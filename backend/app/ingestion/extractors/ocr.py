"""OCR through Tesseract (worker only). Document text is never logged."""

from __future__ import annotations

import shutil
from typing import Any

from app.ingestion.extractors.base import OCR_UNAVAILABLE, ExtractionError, ExtractionLimits


def ocr_available() -> bool:
    return shutil.which("tesseract") is not None


def ocr_image(image: Any, limits: ExtractionLimits) -> tuple[str, list[float]]:
    """Run Tesseract on a PIL image. Returns (text, per-word confidences 0-100).

    Raises ExtractionError(OCR_UNAVAILABLE) when the engine is missing or fails, so a page that
    needs OCR never silently yields nothing."""
    if not ocr_available():
        raise ExtractionError(OCR_UNAVAILABLE, "OCR is not available on this worker.")
    import pytesseract
    from PIL import Image

    # PIL keeps this limit globally; set it on every call so no earlier caller's value lingers.
    Image.MAX_IMAGE_PIXELS = limits.image_max_pixels
    try:
        data = pytesseract.image_to_data(
            image,
            lang=limits.ocr_languages,
            output_type=pytesseract.Output.DICT,
            timeout=limits.ocr_timeout_seconds,
        )
    except (pytesseract.TesseractError, pytesseract.TesseractNotFoundError, RuntimeError):
        raise ExtractionError(OCR_UNAVAILABLE, "OCR failed.") from None
    lines: dict[tuple[int, int, int], list[str]] = {}
    confidences: list[float] = []
    for i, word in enumerate(data["text"]):
        word = word.strip()
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            continue
        if not word or conf < 0:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        lines.setdefault(key, []).append(word)
        confidences.append(conf)
    text = "\n".join(" ".join(words) for _, words in sorted(lines.items()))
    return text, confidences
