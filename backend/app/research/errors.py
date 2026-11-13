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
