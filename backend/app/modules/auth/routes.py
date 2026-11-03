from fastapi import APIRouter, Cookie, Request, Response
from typing import Annotated

from app.core.dependencies import CurrentUser, DbSession
from app.modules.auth.schemas import AuthResponse, LoginRequest, MeResponse, RegisterRequest
from app.modules.auth.service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse, status_code=201)
async def register(
    data: RegisterRequest,
    db: DbSession,
    response: Response,
) -> AuthResponse:
    service = AuthService(db)
    user = await service.register(data, response)
    from app.modules.auth.schemas import UserOut
    return AuthResponse(data=UserOut.model_validate(user))


@router.post("/login", response_model=AuthResponse)
async def login(
    data: LoginRequest,
    request: Request,
    db: DbSession,
    response: Response,
) -> AuthResponse:
    service = AuthService(db)
    user = await service.login(data, request, response)
    from app.modules.auth.schemas import UserOut
    return AuthResponse(data=UserOut.model_validate(user))


@router.post("/logout")
async def logout(
    db: DbSession,
    response: Response,
    aw_session: Annotated[str | None, Cookie()] = None,
) -> dict[str, object]:
    if aw_session:
        service = AuthService(db)
        await service.logout(aw_session, response)
    return {"success": True, "data": None}


@router.get("/me", response_model=MeResponse)
async def me(current_user: CurrentUser) -> MeResponse:
    from app.modules.auth.schemas import UserOut
    return MeResponse(data=UserOut.model_validate(current_user))
