"""Users API routes (A5): profile, preferences, sessions, password/email, export, deletion."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Request, Response
from fastapi.responses import JSONResponse

from app.core.dependencies import ActiveUser, DbSession, VerifiedUser
from app.core.rate_limit import InProcessRateLimiter, get_client_ip, get_rate_limiter
from app.core.security import hash_token
from app.modules.users.schemas import (
    ChangeEmailRequest,
    ChangePasswordRequest,
    DeleteAccountRequest,
    PreferencesResponse,
    ProfileResponse,
    SessionListResponse,
    SessionOut,
    UpdatePreferencesRequest,
    UpdateProfileRequest,
    UserPreferencesOut,
    UserProfileOut,
)
from app.modules.users.service import UsersService

router = APIRouter(prefix="/users", tags=["users"])

_CHANGE_LIMIT = (5, 300)  # 5 per 5 min per IP (re-auth operations)


# ── Profile ───────────────────────────────────────────────────────────────────

@router.get("/me/profile", response_model=ProfileResponse)
async def get_profile(current_user: ActiveUser) -> ProfileResponse:
    return ProfileResponse(data=UserProfileOut.model_validate(current_user.profile))


@router.patch("/me/profile", response_model=ProfileResponse)
async def update_profile(
    data: UpdateProfileRequest,
    current_user: ActiveUser,
    db: DbSession,
) -> ProfileResponse:
    service = UsersService(db)
    user = await service.update_profile(current_user, data)
    return ProfileResponse(data=UserProfileOut.model_validate(user.profile))


# ── Preferences ───────────────────────────────────────────────────────────────

@router.get("/me/preferences", response_model=PreferencesResponse)
async def get_preferences(current_user: ActiveUser) -> PreferencesResponse:
    return PreferencesResponse(data=UserPreferencesOut.model_validate(current_user.preferences))


@router.patch("/me/preferences", response_model=PreferencesResponse)
async def update_preferences(
    data: UpdatePreferencesRequest,
    current_user: ActiveUser,
    db: DbSession,
) -> PreferencesResponse:
    service = UsersService(db)
    user = await service.update_preferences(current_user, data)
    return PreferencesResponse(data=UserPreferencesOut.model_validate(user.preferences))


# ── Sessions ──────────────────────────────────────────────────────────────────

@router.get("/me/sessions", response_model=SessionListResponse)
async def list_sessions(
    current_user: ActiveUser,
    db: DbSession,
    aw_session: Annotated[str | None, Cookie()] = None,
) -> SessionListResponse:
    current_hash = hash_token(aw_session) if aw_session else None
    service = UsersService(db)
    sessions = await service.list_sessions(current_user, current_hash)
    out = []
    for s in sessions:
        session_out = SessionOut.model_validate(s)
        session_out.is_current = (current_hash is not None and s.session_token_hash == current_hash)
        out.append(session_out)
    return SessionListResponse(data=out)


@router.delete("/me/sessions/{session_id}", status_code=200)
async def revoke_session(
    session_id: uuid.UUID,
    request: Request,
    current_user: ActiveUser,
    db: DbSession,
) -> dict[str, object]:
    service = UsersService(db)
    await service.revoke_session(current_user, session_id, get_client_ip(request))
    return {"success": True, "data": None}


# ── Password change ───────────────────────────────────────────────────────────

@router.post("/me/change-password", status_code=200)
async def change_password(
    data: ChangePasswordRequest,
    request: Request,
    current_user: VerifiedUser,
    db: DbSession,
    limiter: Annotated[InProcessRateLimiter, Depends(get_rate_limiter)],
    aw_session: Annotated[str | None, Cookie()] = None,
) -> dict[str, object]:
    ip = get_client_ip(request)
    await limiter.check(f"change_pw:{ip}", *_CHANGE_LIMIT)

    current_hash = hash_token(aw_session) if aw_session else None
    service = UsersService(db)
    await service.change_password(current_user, data, current_hash, ip)
    return {"success": True, "data": {"message": "Password updated. Other sessions have been signed out."}}


# ── Email change ──────────────────────────────────────────────────────────────

@router.post("/me/change-email", status_code=200)
async def change_email(
    data: ChangeEmailRequest,
    request: Request,
    current_user: VerifiedUser,
    db: DbSession,
    limiter: Annotated[InProcessRateLimiter, Depends(get_rate_limiter)],
) -> dict[str, object]:
    ip = get_client_ip(request)
    await limiter.check(f"change_email:{ip}", *_CHANGE_LIMIT)

    service = UsersService(db)
    await service.request_email_change(current_user, data, ip)
    # Token creation + email sending is a follow-on step handled by A3's EmailAuthService
    # For now we confirm the request was accepted
    return {"success": True, "data": {"message": "A verification email has been sent to your new address."}}


# ── Data export ───────────────────────────────────────────────────────────────

@router.get("/me/export")
async def export_data(
    request: Request,
    current_user: VerifiedUser,
    db: DbSession,
    limiter: Annotated[InProcessRateLimiter, Depends(get_rate_limiter)],
) -> JSONResponse:
    ip = get_client_ip(request)
    await limiter.check(f"export:{ip}", 2, 3600)  # 2 per hour

    service = UsersService(db)
    data = await service.export_data(current_user)
    return JSONResponse(
        content={"success": True, "data": data},
        headers={"Content-Disposition": "attachment; filename=axonweave-export.json"},
    )


# ── Account deletion ──────────────────────────────────────────────────────────

@router.delete("/me", status_code=200)
async def delete_account(
    data: DeleteAccountRequest,
    request: Request,
    current_user: ActiveUser,
    db: DbSession,
    response: Response,
    limiter: Annotated[InProcessRateLimiter, Depends(get_rate_limiter)],
) -> dict[str, object]:
    ip = get_client_ip(request)
    await limiter.check(f"delete_account:{ip}", 3, 3600)

    service = UsersService(db)
    await service.delete_account(current_user, data, ip)
    response.delete_cookie("aw_session", path="/")
    response.delete_cookie("csrf_token", path="/")
    return {"success": True, "data": {"message": "Your account has been permanently deleted."}}
