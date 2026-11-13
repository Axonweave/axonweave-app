"""Research Studio errors. Fixed code, status and message; messages never contain user content."""

from __future__ import annotations

from app.ai.errors import AiError


class ResearchError(AiError):
    """Base for Research Studio errors (rendered by the shared AiError handler)."""


class ProjectNotFoundError(ResearchError):
    code = "RESOURCE_NOT_FOUND"
    http_status = 404
    user_message = "Research project not found."


class WorkspaceNotFoundError(ResearchError):
    code = "RESOURCE_NOT_FOUND"
    http_status = 404
    user_message = "Workspace not found."


class InvalidProjectDatesError(ResearchError):
    code = "VALIDATION_ERROR"
    http_status = 422
    user_message = "The target date cannot be before the start date."


class ProjectArchivedError(ResearchError):
    code = "RESEARCH_PROJECT_ARCHIVED"
    http_status = 409
    user_message = "This research project is archived. Restore it to change it."


class ProjectNotArchivedError(ResearchError):
    code = "RESEARCH_PROJECT_NOT_ARCHIVED"
    http_status = 409
    user_message = "This research project is not archived."


class PaperNotFoundError(ResearchError):
    code = "RESOURCE_NOT_FOUND"
    http_status = 404
    user_message = "Paper not found."


class DocumentNotFoundError(ResearchError):
    code = "RESOURCE_NOT_FOUND"
    http_status = 404
    user_message = "Document not found."


class DuplicateDoiError(ResearchError):
    code = "RESEARCH_DUPLICATE_DOI"
    http_status = 409
    user_message = "A paper with this DOI is already in this project."


class DocumentAlreadyLinkedError(ResearchError):
    code = "RESEARCH_DOCUMENT_ALREADY_LINKED"
    http_status = 409
    user_message = "This document is already attached to a paper in this project."


class PaperArchivedError(ResearchError):
    code = "RESEARCH_PAPER_ARCHIVED"
    http_status = 409
    user_message = "This paper is archived. Restore it to change it."


class PaperNotArchivedError(ResearchError):
    code = "RESEARCH_PAPER_NOT_ARCHIVED"
    http_status = 409
    user_message = "This paper is not archived."


class InvalidMergeError(ResearchError):
    code = "RESEARCH_INVALID_MERGE"
    http_status = 422
    user_message = "Choose one of the two papers to keep."


# Paper analysis (M7.3) ───────────────────────────────────────────────────────
class AnalysisNotFoundError(ResearchError):
    code = "RESOURCE_NOT_FOUND"
    http_status = 404
    user_message = "Analysis not found."


class NoteNotFoundError(ResearchError):
    code = "RESOURCE_NOT_FOUND"
    http_status = 404
    user_message = "Note not found."


class PaperHasNoFileError(ResearchError):
    code = "RESEARCH_PAPER_HAS_NO_FILE"
    http_status = 422
    user_message = "Attach a PDF to this paper before analysing it."


class PaperFileNotReadyError(ResearchError):
    code = "RESEARCH_DOCUMENT_NOT_READY"
    http_status = 422
    user_message = "The paper file has not finished processing yet."


class AnalysisUnavailableError(ResearchError):
    code = "RESEARCH_ANALYSIS_UNAVAILABLE"
    http_status = 503
    user_message = "Paper analysis is not available right now. Try again later."


class AnalysisRateLimitedError(ResearchError):
    code = "RESEARCH_RATE_LIMITED"
    http_status = 429
    user_message = "Too many analysis requests. Try again shortly."


class TooManyActiveAnalysesError(ResearchError):
    code = "RESEARCH_TOO_MANY_ACTIVE"
    http_status = 429
    user_message = "You already have analyses running. Wait for one to finish."


class AnalysisNotCancellableError(ResearchError):
    code = "RESEARCH_NOT_CANCELLABLE"
    http_status = 409
    user_message = "This analysis has already finished."


# Codes stored on a failed analysis (fixed vocabulary; never provider or paper text).
INVALID_OUTPUT = "RESEARCH_INVALID_OUTPUT"
NOTHING_VERIFIED = "RESEARCH_NOTHING_VERIFIED"
TIMEOUT = "RESEARCH_TIMEOUT"
INTERRUPTED = "RESEARCH_INTERRUPTED"
SOURCES_GONE = "RESEARCH_DOCUMENT_NOT_READY"
TOO_LARGE = "RESEARCH_SOURCE_TOO_LARGE"
INTERNAL = "RESEARCH_ANALYSIS_FAILED"
CANCELLED = "RESEARCH_CANCELLED"

_MESSAGES = {
    INVALID_OUTPUT: "The AI reply could not be used. Try again.",
    NOTHING_VERIFIED: "Nothing could be confirmed against the paper text.",
    TIMEOUT: "The analysis took too long and was stopped.",
    INTERRUPTED: "The analysis was interrupted. Try again.",
    SOURCES_GONE: "The paper file is no longer available or not ready.",
    TOO_LARGE: "The paper is too large to analyse in one run.",
    INTERNAL: "The analysis failed. Try again.",
    CANCELLED: "The analysis was cancelled.",
}


def safe_analysis_message(code: str | None) -> str | None:
    if not code:
        return None
    return _MESSAGES.get(code, _MESSAGES[INTERNAL])


# Paper comparison (M7.4) ─────────────────────────────────────────────────────
class ComparisonNotFoundError(ResearchError):
    code = "RESOURCE_NOT_FOUND"
    http_status = 404
    user_message = "Comparison not found."


class PaperNotAnalysedError(ResearchError):
    code = "RESEARCH_PAPER_NOT_ANALYSED"
    http_status = 422
    user_message = "Every paper in a comparison needs a completed analysis first."


# Evidence matrix (M7.5) ──────────────────────────────────────────────────────
class MatrixNotFoundError(ResearchError):
    code = "RESOURCE_NOT_FOUND"
    http_status = 404
    user_message = "Matrix not found."


class MatrixColumnNotFoundError(ResearchError):
    code = "RESOURCE_NOT_FOUND"
    http_status = 404
    user_message = "Column not found."


class MatrixEntryNotFoundError(ResearchError):
    code = "RESOURCE_NOT_FOUND"
    http_status = 404
    user_message = "That paper is not in this matrix."


class DuplicateColumnError(ResearchError):
    code = "RESEARCH_DUPLICATE_COLUMN"
    http_status = 409
    user_message = "A column with that name already exists."


class InvalidColumnOrderError(ResearchError):
    code = "VALIDATION_ERROR"
    http_status = 422
    user_message = "The column order must list every column of the matrix exactly once."


# Research gaps (M7.6)
class GapNotFoundError(ResearchError):
    code = "RESOURCE_NOT_FOUND"
    http_status = 404
    user_message = "Research gap not found."


class NoAnalysedPapersError(ResearchError):
    code = "RESEARCH_NO_ANALYSED_PAPERS"
    http_status = 422
    user_message = "Analyse at least one paper in this project first."


# Contradictions (M7.7)
class ContradictionNotFoundError(ResearchError):
    code = "RESOURCE_NOT_FOUND"
    http_status = 404
    user_message = "Contradiction not found."


class NeedTwoAnalysedPapersError(ResearchError):
    code = "RESEARCH_NEED_TWO_ANALYSED_PAPERS"
    http_status = 422
    user_message = "Analyse at least two papers in this project first."
