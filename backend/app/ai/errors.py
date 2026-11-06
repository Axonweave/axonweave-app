"""Error taxonomy for the AI layer (D-49).

Every provider failure becomes one of these. The message shown to users is fixed per class and never
contains provider text, credentials or request content. `retryable` only applies before the first
streamed token (D-50).
"""

from __future__ import annotations

from fastapi import HTTPException


class AiError(Exception):
    """Base for AI errors that map to an HTTP response."""

    code: str = "LLM_BAD_RESPONSE"
    http_status: int = 502
    retryable: bool = False
    user_message: str = "The AI service returned an unexpected response."

    def __init__(
        self,
        *,
        retry_after: float | None = None,
        provider_request_id: str | None = None,
    ) -> None:
        super().__init__(self.code)
        self.retry_after = retry_after
        self.provider_request_id = provider_request_id

    def to_http_exception(self) -> HTTPException:
        headers = None
        if self.retry_after is not None:
            headers = {"Retry-After": str(max(1, int(self.retry_after)))}
        return HTTPException(
            status_code=self.http_status,
            detail={"code": self.code, "message": self.user_message},
            headers=headers,
        )


class LLMError(AiError):
    """A failure talking to, or configuring, a model provider."""


class LLMNotConfiguredError(LLMError):
    code = "LLM_NOT_CONFIGURED"
    http_status = 503
    user_message = "The AI service is not configured."


class LLMAuthFailedError(LLMError):
    code = "LLM_AUTH_FAILED"
    http_status = 502
    user_message = "The AI service is unavailable."


class LLMRateLimitedError(LLMError):
    code = "LLM_RATE_LIMITED"
    http_status = 429
    retryable = True
    user_message = "The AI service is temporarily busy. Please try again."


class LLMTimeoutError(LLMError):
    code = "LLM_TIMEOUT"
    http_status = 504
    retryable = True
    user_message = "The AI service took too long to respond. Please try again."


class LLMUnavailableError(LLMError):
    code = "LLM_UNAVAILABLE"
    http_status = 503
    retryable = True
    user_message = "The AI service is temporarily unavailable. Please try again."


class LLMContextTooLongError(LLMError):
    code = "LLM_CONTEXT_TOO_LONG"
    http_status = 422
    user_message = "This message is too long for the AI model. Please shorten it."


class LLMContentBlockedError(LLMError):
    code = "LLM_CONTENT_BLOCKED"
    http_status = 422
    user_message = "The AI service could not process this request."


class LLMInvalidModelError(LLMError):
    code = "LLM_INVALID_MODEL"
    http_status = 422
    user_message = "That model is not available."


class LLMBadResponseError(LLMError):
    code = "LLM_BAD_RESPONSE"
    http_status = 502
    user_message = "The AI service returned an unexpected response."


class LLMCapabilityError(LLMInvalidModelError):
    """The selected model does not support the requested operation."""

    user_message = "That model does not support this operation."


class AiQuotaExceededError(AiError):
    code = "AI_QUOTA_EXCEEDED"
    http_status = 429
    user_message = "You have reached your AI usage limit. Please try again later."


class GenerationInProgressError(AiError):
    code = "AI_GENERATION_IN_PROGRESS"
    http_status = 409
    user_message = "A response is already being generated. Please wait or stop it first."


class ConversationNotFoundError(AiError):
    code = "CONVERSATION_NOT_FOUND"
    http_status = 404
    user_message = "Conversation not found."


class ConversationArchivedError(AiError):
    code = "CONVERSATION_ARCHIVED"
    http_status = 409
    user_message = "This conversation is archived. Restore it to continue."


class MessageNotFoundError(AiError):
    code = "MESSAGE_NOT_FOUND"
    http_status = 404
    user_message = "Message not found."


class InputTooLongError(AiError):
    code = "AI_INPUT_TOO_LONG"
    http_status = 422
    user_message = "Your message is too long. Please shorten it and try again."


class StreamingNotAvailableError(AiError):
    code = "STREAMING_NOT_AVAILABLE"
    http_status = 400
    user_message = "Streaming responses are not available yet. Send with stream=false."


ALL_ERROR_CODES = frozenset(
    cls.code
    for cls in (
        LLMNotConfiguredError,
        LLMAuthFailedError,
        LLMRateLimitedError,
        LLMTimeoutError,
        LLMUnavailableError,
        LLMContextTooLongError,
        LLMContentBlockedError,
        LLMInvalidModelError,
        LLMBadResponseError,
        AiQuotaExceededError,
        GenerationInProgressError,
        ConversationNotFoundError,
        ConversationArchivedError,
        MessageNotFoundError,
        InputTooLongError,
        StreamingNotAvailableError,
    )
)
