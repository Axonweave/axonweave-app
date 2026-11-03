"""Pydantic schemas for the users module (A5)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, EmailStr, field_validator


# ── Responses ────────────────────────────────────────────────────────────────

class UserProfileOut(BaseModel):
    full_name: str
    avatar_url: str | None
    preferred_language: str
    timezone: str

    model_config = {"from_attributes": True}


class UserPreferencesOut(BaseModel):
    theme: str
    explanation_style: str | None
    academic_level: str | None
    study_preferences: Any
    preferred_language: str | None

    model_config = {"from_attributes": True}


class SessionOut(BaseModel):
    id: UUID
    created_at: datetime
    last_used_at: datetime
    expires_at: datetime
    user_agent: str | None
    ip_address: str | None
    remember_me: bool
    is_current: bool = False

    model_config = {"from_attributes": True}


class ProfileResponse(BaseModel):
    success: bool = True
    data: UserProfileOut


class PreferencesResponse(BaseModel):
    success: bool = True
    data: UserPreferencesOut


class SessionListResponse(BaseModel):
    success: bool = True
    data: list[SessionOut]


# ── Requests ─────────────────────────────────────────────────────────────────

class UpdateProfileRequest(BaseModel):
    full_name: str | None = None
    preferred_language: str | None = None
    timezone: str | None = None

    @field_validator("full_name")
    @classmethod
    def _name_not_empty(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("Full name cannot be empty.")
        return v.strip() if v else v


class UpdatePreferencesRequest(BaseModel):
    theme: str | None = None
    explanation_style: str | None = None
    academic_level: str | None = None
    study_preferences: Any = None
    preferred_language: str | None = None

    @field_validator("theme")
    @classmethod
    def _valid_theme(cls, v: str | None) -> str | None:
        if v is not None and v not in ("light", "dark", "system"):
            raise ValueError("theme must be light, dark, or system.")
        return v


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _pw_length(cls, v: str) -> str:
        if len(v) < 12:
            raise ValueError("Password must be at least 12 characters.")
        if len(v) > 128:
            raise ValueError("Password must be at most 128 characters.")
        return v


class ChangeEmailRequest(BaseModel):
    new_email: EmailStr
    current_password: str


class DeleteAccountRequest(BaseModel):
    password: str
    confirmation: str

    @field_validator("confirmation")
    @classmethod
    def _must_be_delete(cls, v: str) -> str:
        if v.strip().lower() != "delete my account":
            raise ValueError("Type 'delete my account' to confirm.")
        return v
