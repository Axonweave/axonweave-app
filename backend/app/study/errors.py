"""Study generation errors. Same shape as the AI errors (fixed code, status and safe message), so
the existing handler renders them. Job failures store only the `code` (never provider text)."""

from __future__ import annotations

from fastapi import HTTPException

from app.ai.errors import AiError


class StudyError(AiError):
    """Base for generation errors. Messages are fixed and never contain content."""


class GenerationNotFoundError(StudyError):
    code = "GENERATION_NOT_FOUND"
    http_status = 404
    user_message = "Generation not found."


class UnknownGeneratorError(StudyError):
    code = "GENERATION_TYPE_UNKNOWN"
    http_status = 422
    user_message = "That generation type is not available."


class InvalidSettingsError(StudyError):
    code = "GENERATION_SETTINGS_INVALID"
    http_status = 422
    user_message = "The generation settings are not valid."


class NoSourcesError(StudyError):
    code = "GENERATION_NO_SOURCES"
    http_status = 422
    user_message = (
        "There is no processed material to generate from. Wait until your documents are "
        "ready, or choose a different source."
    )


class SourceTooLargeError(StudyError):
    code = "GENERATION_SOURCE_TOO_LARGE"
    http_status = 422
    user_message = "The selected material is too large for this kind of generation."


class MaterialNotFoundError(StudyError):
    code = "RESOURCE_NOT_FOUND"
    http_status = 404
    user_message = "Study material not found."


class MaterialVersionConflictError(StudyError):
    code = "MATERIAL_VERSION_CONFLICT"
    http_status = 409
    user_message = "This material changed since you opened it. Reload it and try again."


class InvalidEditError(StudyError):
    code = "MATERIAL_EDIT_INVALID"
    http_status = 422
    user_message = "The edited content is not valid."

    def __init__(self, problem: str = "") -> None:
        super().__init__()
        self.problem = problem  # field paths and rule names only, never content

    def to_http_exception(self) -> HTTPException:
        message = self.user_message + (f" ({self.problem})" if self.problem else "")
        return HTTPException(
            status_code=self.http_status, detail={"code": self.code, "message": message}
        )


class RegenerationNotPossibleError(StudyError):
    code = "REGENERATION_NOT_POSSIBLE"
    http_status = 422
    user_message = "This material cannot be regenerated from its original source."


class PreviewNotAvailableError(StudyError):
    code = "PREVIEW_NOT_AVAILABLE"
    http_status = 409
    user_message = "There is no preview to apply for this generation."


class PreviewStaleError(StudyError):
    code = "PREVIEW_STALE"
    http_status = 409
    user_message = "The material changed after this preview was made. Regenerate to get a new one."


class SourceTooSmallError(StudyError):
    code = "GENERATION_SOURCE_TOO_SMALL"
    http_status = 422
    user_message = "There is not enough material to generate this. Add more content and try again."


class GenerationUnavailableError(StudyError):
    code = "GENERATION_UNAVAILABLE"
    http_status = 503
    user_message = "Background generation is not available right now."


class GenerationQuotaExceededError(StudyError):
    code = "GENERATION_QUOTA_EXCEEDED"
    http_status = 429
    user_message = "You have reached your daily generation limit. Please try again later."


class TooManyActiveGenerationsError(StudyError):
    code = "GENERATION_TOO_MANY_ACTIVE"
    http_status = 429
    user_message = "You have too many generations running. Wait for one to finish."


class NotCancellableError(StudyError):
    code = "GENERATION_NOT_CANCELLABLE"
    http_status = 409
    user_message = "This generation has already finished."


# Codes recorded on a failed job (never shown with provider text). Also see AiError codes.
INVALID_OUTPUT = "GENERATION_INVALID_OUTPUT"
TIMEOUT = "GENERATION_TIMEOUT"
INTERRUPTED = "GENERATION_INTERRUPTED"
SOURCES_GONE = "GENERATION_NO_SOURCES"
INTERNAL = "GENERATION_FAILED"
CANCELLED = "GENERATION_CANCELLED"

JOB_ERROR_MESSAGES: dict[str, str] = {
    INVALID_OUTPUT: "The AI returned a result that could not be used. Please try again.",
    TIMEOUT: "The generation took too long and was stopped. Please try again.",
    INTERRUPTED: "The generation was interrupted. Please start it again.",
    SOURCES_GONE: NoSourcesError.user_message,
    INTERNAL: "The generation failed. Please try again.",
    "GENERATION_SOURCE_TOO_SMALL": SourceTooSmallError.user_message,
    "GENERATION_SOURCE_TOO_LARGE": SourceTooLargeError.user_message,
    "LLM_NOT_CONFIGURED": "The AI service is not configured.",
    "LLM_RATE_LIMITED": "The AI service is temporarily busy. Please try again.",
    "LLM_TIMEOUT": "The AI service took too long to respond. Please try again.",
    "LLM_UNAVAILABLE": "The AI service is temporarily unavailable. Please try again.",
    "LLM_CONTEXT_TOO_LONG": SourceTooLargeError.user_message,
    "LLM_CONTENT_BLOCKED": "The AI service could not process this material.",
    "LLM_AUTH_FAILED": "The AI service is unavailable.",
    "LLM_BAD_RESPONSE": "The AI service returned an unexpected response.",
    "LLM_INVALID_MODEL": "The AI model is not available.",
}


def safe_job_message(code: str | None) -> str | None:
    """User-facing text for a stored error code; unknown codes get the generic message."""
    if code is None:
        return None
    return JOB_ERROR_MESSAGES.get(code, JOB_ERROR_MESSAGES[INTERNAL])


class FlashcardNotFoundError(StudyError):
    code = "RESOURCE_NOT_FOUND"
    http_status = 404
    user_message = "Flashcard not found."


class DuplicateFlashcardError(StudyError):
    code = "FLASHCARD_DUPLICATE"
    http_status = 409
    user_message = "A very similar card already exists in this set."


class FlashcardLimitError(StudyError):
    code = "FLASHCARD_LIMIT"
    http_status = 409
    user_message = "This set has reached the maximum number of cards."
