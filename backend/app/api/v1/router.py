from fastapi import APIRouter

from app.modules.auth.routes import router as auth_router
from app.modules.chapters.routes import router as chapters_router
from app.modules.folders.routes import router as folders_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(folders_router)
router.include_router(chapters_router)
