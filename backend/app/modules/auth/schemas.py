import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.core.security import is_password_compromised

TERMS_VERSION = "1.0"


class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    confirm_password: str
    terms_accepted: bool

    @field_validator("password")
    @classmethod
    def _password_strength(cls, v: str) -> str:
        if is_password_compromised(v):
            raise ValueError("This password is too common. Please choose a different password.")
        return v

    @model_validator(mode="after")
    def _passwords_match(self) -> "RegisterRequest":
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match.")
        return self

    @model_validator(mode="after")
    def _terms_required(self) -> "RegisterRequest":
        if not self.terms_accepted:
            raise ValueError("You must accept the terms to register.")
        return self


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    remember_me: bool = False


class UserProfileOut(BaseModel):
    full_name: str
    avatar_url: str | None
    preferred_language: str
    timezone: str

    model_config = {"from_attributes": True}


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    is_verified: bool
    status: str
    created_at: datetime
    profile: UserProfileOut | None

    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    success: bool = True
    data: UserOut


class MeResponse(BaseModel):
    success: bool = True
    data: UserOut
