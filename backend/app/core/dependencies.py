from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_db
from app.models.user import User

# Re-exported session dep
DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    db: DbSession,
    aw_session: Annotated[str | None, Cookie()] = None,
) -> User:
    """Resolve session cookie → User. Raises 401 if missing/invalid."""
    if not aw_session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "NOT_AUTHENTICATED", "message": "Authentication required."},
        )
    # Import here to avoid circular dependency
    from app.modules.auth.service import AuthService

    service = AuthService(db)
    user = await service.get_current_session_user(aw_session)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "SESSION_INVALID", "message": "Session expired or invalid."},
        )
    return user


async def require_active_user(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Like get_current_user but also checks account is active."""
    if user.status not in ("active", "pending_verification"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "ACCOUNT_INACTIVE", "message": "Account is not active."},
        )
    return user


async def require_verified_user(
    user: Annotated[User, Depends(require_active_user)],
) -> User:
    """Requires active account AND verified email (D-16)."""
    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "EMAIL_NOT_VERIFIED", "message": "Email verification required for this action."},
        )
    return user


# Convenience type aliases for route signatures
CurrentUser = Annotated[User, Depends(get_current_user)]
ActiveUser = Annotated[User, Depends(require_active_user)]
VerifiedUser = Annotated[User, Depends(require_verified_user)]
