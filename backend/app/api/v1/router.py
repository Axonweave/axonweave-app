from fastapi import APIRouter

from app.modules.auth.routes import router as auth_router
from app.modules.dashboard.routes import router as dashboard_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(dashboard_router)
