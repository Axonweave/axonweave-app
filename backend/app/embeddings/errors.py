"""Embedding error taxonomy (D-69). Codes and messages are fixed: vendor text is never returned
or logged, and nothing here contains document text."""


class EmbeddingError(Exception):
    code = "EMBEDDING_ERROR"
    user_message = "Embedding failed."
    transient = False  # worth retrying later (rate limit, timeout, outage)

    def __init__(self) -> None:
        super().__init__(self.user_message)


class EmbeddingNotConfiguredError(EmbeddingError):
    code = "EMBEDDING_NOT_CONFIGURED"
    user_message = "No embedding provider is configured."


class EmbeddingAuthFailedError(EmbeddingError):
    code = "EMBEDDING_AUTH_FAILED"
    user_message = "The embedding provider rejected the credentials."


class EmbeddingInvalidModelError(EmbeddingError):
    code = "EMBEDDING_INVALID_MODEL"
    user_message = "The configured embedding model is not available."


class EmbeddingRateLimitedError(EmbeddingError):
    code = "EMBEDDING_RATE_LIMITED"
    user_message = "The embedding provider is rate limiting requests."
    transient = True


class EmbeddingTimeoutError(EmbeddingError):
    code = "EMBEDDING_TIMEOUT"
    user_message = "The embedding provider timed out."
    transient = True


class EmbeddingUnavailableError(EmbeddingError):
    code = "EMBEDDING_UNAVAILABLE"
    user_message = "The embedding provider is unavailable."
    transient = True


class EmbeddingBadResponseError(EmbeddingError):
    code = "EMBEDDING_BAD_RESPONSE"
    user_message = "The embedding provider returned an unusable response."


class EmbeddingDimensionMismatchError(EmbeddingError):
    code = "EMBEDDING_DIMENSION_MISMATCH"
    user_message = "The embedding has an unexpected size."


class EmbeddingQuotaExceededError(EmbeddingError):
    code = "EMBEDDING_QUOTA_EXCEEDED"
    user_message = "The daily token quota is used up."
