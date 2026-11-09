"""Shared types for the extractors. Extraction runs only in the worker (D-70).

Nothing here logs document text: errors carry a safe code and a fixed message.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class ExtractionError(Exception):
    """A document that cannot be processed. `code` is safe to store and show; the text is fixed."""

    def __init__(self, code: str, message: str = "The document could not be processed.") -> None:
        super().__init__(message)
        self.code = code


# Codes written to document_processing_jobs.error_code by the pipeline (spec 17.3).
FILE_CORRUPT = "FILE_CORRUPT"
FILE_ENCRYPTED = "FILE_ENCRYPTED"
TOO_MANY_PAGES = "TOO_MANY_PAGES"
NO_TEXT_FOUND = "NO_TEXT_FOUND"
OCR_UNAVAILABLE = "OCR_UNAVAILABLE"
UNSUPPORTED_FILE_TYPE = "UNSUPPORTED_FILE_TYPE"
FILE_CHECKSUM_MISMATCH = "FILE_CHECKSUM_MISMATCH"

# Safe warning codes stored on the version (never free text).
WARN_OCR_USED = "OCR_USED"
WARN_LOW_OCR_CONFIDENCE = "LOW_OCR_CONFIDENCE"
WARN_PAGES_WITHOUT_TEXT = "PAGES_WITHOUT_TEXT"
WARN_TEXT_TRUNCATED = "TEXT_TRUNCATED"
WARN_OCR_SKIPPED = "OCR_SKIPPED"
WARN_IMAGES_IGNORED = "IMAGES_IGNORED"

LOW_OCR_CONFIDENCE = 60.0  # mean Tesseract word confidence (0-100) below this raises a warning


@dataclass(frozen=True)
class ExtractionLimits:
    max_pages: int
    max_chars: int
    ocr_enabled: bool
    ocr_dpi: int
    ocr_languages: str
    image_max_pixels: int
    ocr_timeout_seconds: int = 60


@dataclass
class Block:
    """One piece of extracted text with where it came from."""

    text: str
    page: int | None = None
    slide: int | None = None
    kind: str = "paragraph"  # heading | paragraph | list | table | notes
    heading: str | None = None  # the section heading in force (filled by the structure pass)
    level: int = 0  # heading level (1 = top) when kind == "heading"
    bbox: tuple[float, float, float, float] | None = None  # PDF page coordinates (points)
    from_ocr: bool = False


@dataclass
class Extraction:
    blocks: list[Block]
    method: str
    page_count: int | None = None
    slide_count: int | None = None
    ocr_used: bool = False
    ocr_confidences: list[float] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ocr_mean_confidence(self) -> float | None:
        if not self.ocr_confidences:
            return None
        return sum(self.ocr_confidences) / len(self.ocr_confidences)

    def add_warning(self, code: str) -> None:
        if code not in self.warnings:
            self.warnings.append(code)


class CharBudget:
    """Stops extraction once `max_chars` of text have been collected (spec 4.5)."""

    def __init__(self, max_chars: int) -> None:
        self.max_chars = max_chars
        self.used = 0
        self.exceeded = False

    def take(self, text: str) -> str | None:
        if self.exceeded:
            return None
        remaining = self.max_chars - self.used
        if len(text) > remaining:
            self.exceeded = True
            text = text[: max(remaining, 0)]
        self.used += len(text)
        return text or None
