"""Dashboard routes (Phase 7 M7.11). Read-only; every route needs an active session and a foreign
project id is a 404."""

import uuid

from fastapi import APIRouter

from app.core.dependencies import ActiveUser, DbSession
from app.modules.research.dashboard_schemas import ResearchDashboardResponse
from app.modules.research.dashboard_service import ResearchDashboardService

router = APIRouter(prefix="/research", tags=["research"])


@router.get("/dashboard", response_model=ResearchDashboardResponse)
async def research_dashboard(
    current_user: ActiveUser, db: DbSession, workspace_id: uuid.UUID | None = None
) -> ResearchDashboardResponse:
    return ResearchDashboardResponse(
        data=await ResearchDashboardService(db).overview(current_user.id, workspace_id)
    )


@router.get("/projects/{project_id}/dashboard", response_model=ResearchDashboardResponse)
async def project_dashboard(
    project_id: uuid.UUID, current_user: ActiveUser, db: DbSession
) -> ResearchDashboardResponse:
    return ResearchDashboardResponse(
        data=await ResearchDashboardService(db).project(current_user.id, project_id)
    )
