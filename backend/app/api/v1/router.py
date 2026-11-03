from fastapi import APIRouter

from app.modules.auth.email_routes import router as email_auth_router
from app.modules.auth.routes import router as auth_router
from app.modules.chapters.routes import router as chapters_router
from app.modules.folders.routes import router as folders_router
from app.modules.subjects.routes import router as subjects_router
from app.modules.users.routes import router as users_router
from app.modules.workspaces.routes import router as workspaces_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(email_auth_router)
router.include_router(users_router)
router.include_router(workspaces_router)
router.include_router(subjects_router)
router.include_router(folders_router)
router.include_router(chapters_router)
