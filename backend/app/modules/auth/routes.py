from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Request, Response

from app.core.dependencies import CurrentUser, DbSession
from app.core.rate_limit import InProcessRateLimiter, get_client_ip, get_rate_limiter
from app.core.security_logging import (
    log_login_failure,
    log_login_success,
    log_logout,
    log_registration,
)
from app.modules.auth.schemas import AuthResponse, LoginRequest, MeResponse, RegisterRequest
from app.modules.auth.service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])

# Rate limit windows (D-18): 10 register / 20 login / 5 logout per 15 min per IP
_REGISTER_LIMIT = (10, 900)
_LOGIN_LIMIT = (20, 900)
_LOGOUT_LIMIT = (5, 900)


@router.post("/register", response_model=AuthResponse, status_code=201)
async def register(
    data: RegisterRequest,
    request: Request,
    db: DbSession,
    response: Response,
    limiter: Annotated[InProcessRateLimiter, Depends(get_rate_limiter)],
) -> AuthResponse:
    ip = get_client_ip(request)
    await limiter.check(f"register:{ip}", *_REGISTER_LIMIT)

    service = AuthService(db)
    user = await service.register(data, response)
    log_registration(str(user.id), ip)

    from app.modules.auth.schemas import UserOut
    return AuthResponse(data=UserOut.model_validate(user))


@router.post("/login", response_model=AuthResponse)
async def login(
    data: LoginRequest,
    request: Request,
    db: DbSession,
    response: Response,
    limiter: Annotated[InProcessRateLimiter, Depends(get_rate_limiter)],
) -> AuthResponse:
    ip = get_client_ip(request)
    await limiter.check(f"login:{ip}", *_LOGIN_LIMIT)
    # Also rate-limit by email to slow down credential-stuffing on one account
    await limiter.check(f"login_email:{data.email.lower()}", *_LOGIN_LIMIT)

    service = AuthService(db)
    try:
        user = await service.login(data, request, response)
    except Exception:
        log_login_failure(ip, "bad_credentials_or_inactive")
        raise

    log_login_success(str(user.id), ip)
    from app.modules.auth.schemas import UserOut
    return AuthResponse(data=UserOut.model_validate(user))


@router.post("/logout")
async def logout(
    request: Request,
    db: DbSession,
    response: Response,
    limiter: Annotated[InProcessRateLimiter, Depends(get_rate_limiter)],
    aw_session: Annotated[str | None, Cookie()] = None,
) -> dict[str, object]:
    ip = get_client_ip(request)
    await limiter.check(f"logout:{ip}", *_LOGOUT_LIMIT)

    if aw_session:
        service = AuthService(db)
        session_user = await service.get_current_session_user(aw_session)
        await service.logout(aw_session, response)
        if session_user:
            log_logout(str(session_user.id), ip)
    return {"success": True, "data": None}


@router.get("/me", response_model=MeResponse)
async def me(current_user: CurrentUser) -> MeResponse:
    from app.modules.auth.schemas import UserOut
    return MeResponse(data=UserOut.model_validate(current_user))
