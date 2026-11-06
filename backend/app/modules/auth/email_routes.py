"""Email verification and password reset routes (A3)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, EmailStr, field_validator

from app.core.dependencies import ActiveUser, DbSession
from app.core.email import EmailSender, get_email_sender
from app.core.rate_limit import RateLimiter, get_client_ip, get_rate_limiter
from app.modules.auth.email_service import EmailAuthService

router = APIRouter(prefix="/auth", tags=["auth"])

_FORGOT_LIMIT = (5, 900)  # 5 per 15 min per IP
_VERIFY_LIMIT = (10, 3600)  # 10 per hour per IP
_RESEND_LIMIT = (3, 3600)  # 3 resends per hour per IP


def _make_service(
    db: DbSession, sender: EmailSender = Depends(get_email_sender)
) -> EmailAuthService:  # type: ignore[assignment]
    return EmailAuthService(db, sender)


# ── Schemas ──────────────────────────────────────────────────────────────────


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _pw_length(cls, v: str) -> str:
        if len(v) < 12:
            raise ValueError("Password must be at least 12 characters.")
        if len(v) > 128:
            raise ValueError("Password must be at most 128 characters.")
        return v


class VerifyEmailRequest(BaseModel):
    token: str


# ── Routes ───────────────────────────────────────────────────────────────────


@router.post("/forgot-password", status_code=200)
async def forgot_password(
    data: ForgotPasswordRequest,
    request: Request,
    db: DbSession,
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> dict[str, object]:
    ip = get_client_ip(request)
    await limiter.check(f"forgot:{ip}", *_FORGOT_LIMIT)

    sender = get_email_sender()
    service = EmailAuthService(db, sender)
    await service.forgot_password(str(data.email), ip)
    # Always return the same response — never leak whether email exists
    return {
        "success": True,
        "data": {"message": "If an account with that email exists, a reset link has been sent."},
    }


@router.post("/reset-password", status_code=200)
async def reset_password(
    data: ResetPasswordRequest,
    request: Request,
    db: DbSession,
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> dict[str, object]:
    ip = get_client_ip(request)
    await limiter.check(f"reset:{ip}", *_FORGOT_LIMIT)

    sender = get_email_sender()
    service = EmailAuthService(db, sender)
    await service.reset_password(data.token, data.new_password, ip)
    return {"success": True, "data": {"message": "Password has been reset. Please log in again."}}


@router.post("/verify-email", status_code=200)
async def verify_email(
    data: VerifyEmailRequest,
    request: Request,
    db: DbSession,
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> dict[str, object]:
    ip = get_client_ip(request)
    await limiter.check(f"verify:{ip}", *_VERIFY_LIMIT)

    sender = get_email_sender()
    service = EmailAuthService(db, sender)
    await service.verify_email(data.token, ip)
    return {"success": True, "data": {"message": "Email verified successfully."}}


@router.post("/resend-verification", status_code=200)
async def resend_verification(
    request: Request,
    current_user: ActiveUser,
    db: DbSession,
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> dict[str, object]:
    ip = get_client_ip(request)
    await limiter.check(f"resend:{ip}", *_RESEND_LIMIT)

    sender = get_email_sender()
    service = EmailAuthService(db, sender)
    await service.resend_verification(current_user)
    return {"success": True, "data": {"message": "Verification email sent."}}
