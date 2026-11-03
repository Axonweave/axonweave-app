from fastapi import APIRouter, Query

from app.core.dependencies import ActiveUser, DbSession
from app.modules.dashboard.schemas import ActivityResponse, DashboardStatsResponse
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
