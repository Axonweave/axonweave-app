from fastapi import APIRouter

from app.modules.auth.routes import router as auth_router
from app.modules.subjects.routes import router as subjects_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(subjects_router)
