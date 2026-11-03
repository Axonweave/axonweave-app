from fastapi import APIRouter

from app.modules.auth.email_routes import router as email_auth_router
from app.modules.auth.routes import router as auth_router
from app.modules.users.routes import router as users_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(email_auth_router)
router.include_router(users_router)
