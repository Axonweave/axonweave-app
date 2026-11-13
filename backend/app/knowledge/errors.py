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


# Graph errors (Milestone 6.3). Non-owned resources are 404, never 403 (rule 2).
class NodeNotFoundError(KnowledgeError):
    code = "RESOURCE_NOT_FOUND"
    http_status = 404
    user_message = "Concept not found."


class EdgeNotFoundError(KnowledgeError):
    code = "RESOURCE_NOT_FOUND"
    http_status = 404
    user_message = "Relationship not found."


class CandidateNotFoundError(KnowledgeError):
    code = "RESOURCE_NOT_FOUND"
    http_status = 404
    user_message = "Suggestion not found."


class ScopeNotFoundError(KnowledgeError):
    code = "RESOURCE_NOT_FOUND"
    http_status = 404
    user_message = "Workspace, subject or chapter not found."


class DuplicateConceptError(KnowledgeError):
    code = "KNOWLEDGE_DUPLICATE_CONCEPT"
    http_status = 409
    user_message = "A concept with that name and type already exists in this workspace."


class AliasConflictError(KnowledgeError):
    code = "KNOWLEDGE_ALIAS_CONFLICT"
    http_status = 409
    user_message = "One of those aliases already belongs to another concept."


class DuplicateRelationshipError(KnowledgeError):
    code = "KNOWLEDGE_DUPLICATE_RELATIONSHIP"
    http_status = 409
    user_message = "That relationship already exists."


class InvalidRelationshipError(KnowledgeError):
    code = "KNOWLEDGE_INVALID_RELATIONSHIP"
    http_status = 422
    user_message = "A relationship needs two different concepts from the same workspace."


class NodeNotArchivedError(KnowledgeError):
    code = "KNOWLEDGE_NOT_ARCHIVED"
    http_status = 409
    user_message = "Archive the concept before deleting it permanently."


class InvalidMergeError(KnowledgeError):
    code = "KNOWLEDGE_INVALID_MERGE"
    http_status = 422
    user_message = "Only two different concepts from the same workspace can be merged."


class InvalidCandidateActionError(KnowledgeError):
    code = "KNOWLEDGE_INVALID_ACTION"
    http_status = 422
    user_message = "That action is not valid for this suggestion."


class ConceptLinkNotFoundError(KnowledgeError):
    code = "RESOURCE_NOT_FOUND"
    http_status = 404
    user_message = "Concept link not found."
