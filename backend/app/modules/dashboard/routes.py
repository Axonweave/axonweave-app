from fastapi import APIRouter, Query

from app.core.dependencies import ActiveUser, DbSession
from app.modules.dashboard.schemas import (
    ActivityResponse,
    ArchivedResponse,
    DashboardStatsResponse,
    RecentSubjectsResponse,
    WorkspaceOverviewResponse,
)
from app.modules.dashboard.service import DashboardService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

_MAX_LIMIT = 100


@router.get("/stats", response_model=DashboardStatsResponse)
async def get_stats(
    current_user: ActiveUser,
    db: DbSession,
) -> DashboardStatsResponse:
    service = DashboardService(db)
    stats = await service.get_stats(user_id=current_user.id)
    return DashboardStatsResponse(data=stats)


@router.get("/activity", response_model=ActivityResponse)
async def get_activity(
    current_user: ActiveUser,
    db: DbSession,
    limit: int = Query(default=20, ge=1, le=_MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> ActivityResponse:
    service = DashboardService(db)
    items, total = await service.get_activity(
        user_id=current_user.id,
        limit=limit,
        offset=offset,
    )
    return ActivityResponse(data=items, total=total)


@router.get("/workspaces", response_model=WorkspaceOverviewResponse)
async def get_workspace_overview(
    current_user: ActiveUser,
    db: DbSession,
    limit: int = Query(default=6, ge=1, le=_MAX_LIMIT),
) -> WorkspaceOverviewResponse:
    service = DashboardService(db)
    items, total = await service.get_workspace_overview(user_id=current_user.id, limit=limit)
    return WorkspaceOverviewResponse(data=items, total=total)


@router.get("/recent-subjects", response_model=RecentSubjectsResponse)
async def get_recent_subjects(
    current_user: ActiveUser,
    db: DbSession,
    limit: int = Query(default=5, ge=1, le=20),
) -> RecentSubjectsResponse:
    service = DashboardService(db)
    items = await service.get_recent_subjects(user_id=current_user.id, limit=limit)
    return RecentSubjectsResponse(data=items)


@router.get("/archived", response_model=ArchivedResponse)
async def get_archived(
    current_user: ActiveUser,
    db: DbSession,
    limit: int = Query(default=20, ge=1, le=_MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> ArchivedResponse:
    service = DashboardService(db)
    items, total = await service.get_archived(user_id=current_user.id, limit=limit, offset=offset)
    return ArchivedResponse(data=items, total=total)
