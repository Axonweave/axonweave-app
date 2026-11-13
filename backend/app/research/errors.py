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
