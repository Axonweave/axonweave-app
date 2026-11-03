from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Request, Response

from app.core.dependencies import CurrentUser, DbSession
from app.core.email import EmailSender, get_email_sender
from app.modules.auth.email_service import EmailAuthService
from app.modules.auth.schemas import AuthResponse, LoginRequest, MeResponse, RegisterRequest
from app.modules.auth.service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse, status_code=201)
async def register(
    data: RegisterRequest,
    request: Request,
    db: DbSession,
    response: Response,
    sender: Annotated[EmailSender, Depends(get_email_sender)],
) -> AuthResponse:
    service = AuthService(db)
    user = await service.register(data, response)

    # Send verification email — fire-and-forget style (failure is logged, not raised)
    try:
        email_svc = EmailAuthService(db, sender)
        await email_svc.send_verification_email(user)
    except Exception as exc:
        from app.core.logging import get_logger
        get_logger(__name__).error("verification_email_failed", error=str(exc), user_id=str(user.id))

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
