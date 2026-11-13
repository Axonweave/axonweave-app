"""Errors of the revision feature. Same pattern as the study errors: a stable code, an HTTP status
and a safe message. A foreign or missing card or session is always a 404."""

from app.study.errors import StudyError


class CardNotFoundError(StudyError):
    code = "RESOURCE_NOT_FOUND"
    http_status = 404
    user_message = "Flashcard not found."


class SessionNotFoundError(StudyError):
    code = "RESOURCE_NOT_FOUND"
    http_status = 404
    user_message = "Revision session not found."


class CardSuspendedError(StudyError):
    code = "CARD_SUSPENDED"
    http_status = 409
    user_message = "This card is suspended. Unsuspend it to review it."


class NothingDueError(StudyError):
    code = "NOTHING_DUE"
    http_status = 409
    user_message = "There is nothing to revise right now."


class SessionNotActiveError(StudyError):
    code = "SESSION_NOT_ACTIVE"
    http_status = 409
    user_message = "This revision session is no longer active."


class CardNotInSessionError(StudyError):
    code = "CARD_NOT_IN_SESSION"
    http_status = 422
    user_message = "That card is not part of this revision session."


class ReviewRateLimitedError(StudyError):
    code = "REVIEW_RATE_LIMITED"
    http_status = 429
    user_message = "You are reviewing very quickly. Please wait a moment."


class InvalidStateError(StudyError):
    code = "SCHEDULE_STATE_INVALID"
    http_status = 409
    user_message = "This card's schedule could not be read. Reset is not available yet."
