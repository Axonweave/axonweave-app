"""Knowledge errors. Same shape as the AI and study errors (fixed code, status, safe message); job
failures store only the `code` (never provider text or document text)."""

from __future__ import annotations

from app.ai.errors import AiError


class KnowledgeError(AiError):
    """Base for knowledge errors. Messages are fixed and never contain content."""


class ExtractionJobNotFoundError(KnowledgeError):
    code = "RESOURCE_NOT_FOUND"
    http_status = 404
    user_message = "Extraction job not found."


class DocumentNotReadyError(KnowledgeError):
    code = "KNOWLEDGE_DOCUMENT_NOT_READY"
    http_status = 422
    user_message = "This document has not finished processing, so concepts cannot be extracted yet."


class ExtractionUnavailableError(KnowledgeError):
    code = "KNOWLEDGE_UNAVAILABLE"
    http_status = 503
    user_message = "Concept extraction is not available right now. Try again later."


class ExtractionRateLimitedError(KnowledgeError):
    code = "KNOWLEDGE_RATE_LIMITED"
    http_status = 429
    user_message = "Too many extraction requests. Try again shortly."


class TooManyActiveExtractionsError(KnowledgeError):
    code = "KNOWLEDGE_TOO_MANY_ACTIVE"
    http_status = 429
    user_message = "You already have extractions running. Wait for one to finish."


class ExtractionNotCancellableError(KnowledgeError):
    code = "KNOWLEDGE_NOT_CANCELLABLE"
    http_status = 409
    user_message = "This extraction has already finished."


# Codes stored on a failed job (fixed vocabulary; the user sees the message below).
INVALID_OUTPUT = "KNOWLEDGE_INVALID_OUTPUT"
NOTHING_VERIFIED = "KNOWLEDGE_NOTHING_VERIFIED"
TIMEOUT = "KNOWLEDGE_TIMEOUT"
INTERRUPTED = "KNOWLEDGE_INTERRUPTED"
SOURCES_GONE = "KNOWLEDGE_DOCUMENT_NOT_READY"
TOO_LARGE = "KNOWLEDGE_SOURCE_TOO_LARGE"
INTERNAL = "KNOWLEDGE_FAILED"
CANCELLED = "KNOWLEDGE_CANCELLED"

_MESSAGES = {
    INVALID_OUTPUT: "The AI reply could not be used. Try again.",
    NOTHING_VERIFIED: "No concepts could be confirmed against the document text.",
    TIMEOUT: "The extraction took too long and was stopped.",
    INTERRUPTED: "The extraction was interrupted. Try again.",
    SOURCES_GONE: "The document is no longer available or not ready.",
    TOO_LARGE: "The document is too large to extract in one run.",
    INTERNAL: "The extraction failed. Try again.",
    CANCELLED: "The extraction was cancelled.",
}


def safe_job_message(code: str | None) -> str | None:
    """User text for a stored error code. Unknown codes get the generic message."""
    if not code:
        return None
    return _MESSAGES.get(code, _MESSAGES[INTERNAL])
