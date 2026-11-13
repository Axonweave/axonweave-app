"""Schemas for the Research Studio dashboard (Phase 7 M7.11). Names carry the
`ResearchDashboard` prefix to stay unique across the OpenAPI document."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class ResearchDashboardCounts(BaseModel):
    active_projects: int | None
    papers: int
    papers_analysed: int
    papers_awaiting: int
    papers_failed: int
    comparisons: int
    matrices: int
    candidate_gaps: int
    contradictions_to_review: int
    drafts_in_progress: int


class ResearchDashboardActivity(BaseModel):
    kind: str
    title: str
    research_project_id: uuid.UUID
    project_title: str
    at: datetime


class ResearchDashboardOut(BaseModel):
    counts: ResearchDashboardCounts
    recent: list[ResearchDashboardActivity]


class ResearchDashboardResponse(BaseModel):
    success: bool = True
    data: ResearchDashboardOut
