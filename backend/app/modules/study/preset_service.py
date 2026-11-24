"""Study presets (Study Studio): named sets of generation defaults, several per user, one default.

Every query is scoped to the owner; another user's preset id is a 404. Values are only defaults
(see `preferences_service`): a setting chosen in the generate dialog always wins.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.study_preset import StudyPreset
from app.models.user import User
from app.study.errors import PresetLimitError, PresetNameTakenError, PresetNotFoundError

MAX_PRESETS = 20


class PresetIn(BaseModel):
    """Replaces a preset's contents; a field left out (or null) is cleared."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=60)
    description: str | None = Field(default=None, max_length=200)
    is_default: bool = False
    language: str | None = Field(
        default=None, min_length=2, max_length=32, pattern=r"^[A-Za-z][A-Za-z \-]*$"
    )
    explanation_level: Literal["beginner", "intermediate", "advanced"] | None = None
    summary_length: Literal["short", "medium", "long"] | None = None
    question_difficulty: Literal["easy", "medium", "hard", "mixed"] | None = None
    include_examples: bool = True
    include_definitions: bool = True
    include_source_references: bool = True

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name cannot be blank.")
        return v

    @field_validator("description")
    @classmethod
    def blank_description_is_none(cls, v: str | None) -> str | None:
        return v.strip() if v is not None and v.strip() else None


class PresetOut(PresetIn):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class PresetResponse(BaseModel):
    success: bool = True
    data: PresetOut


class PresetListResponse(BaseModel):
    success: bool = True
    data: list[PresetOut]
    total: int


class StudyPresetService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_owned(self, user_id: uuid.UUID, preset_id: uuid.UUID) -> StudyPreset:
        row = (
            await self._db.execute(
                select(StudyPreset).where(
                    StudyPreset.id == preset_id, StudyPreset.user_id == user_id
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise PresetNotFoundError()
        return row

    async def default_for(self, user_id: uuid.UUID) -> StudyPreset | None:
        return (
            await self._db.execute(
                select(StudyPreset).where(
                    StudyPreset.user_id == user_id, StudyPreset.is_default.is_(True)
                )
            )
        ).scalar_one_or_none()

    async def list(self, user: User) -> list[StudyPreset]:
        rows = await self._db.execute(
            select(StudyPreset)
            .where(StudyPreset.user_id == user.id)
            .order_by(StudyPreset.is_default.desc(), func.lower(StudyPreset.name))
        )
        return list(rows.scalars())

    async def _clear_default(self, user_id: uuid.UUID, except_id: uuid.UUID | None) -> None:
        stmt = update(StudyPreset).where(
            StudyPreset.user_id == user_id, StudyPreset.is_default.is_(True)
        )
        if except_id is not None:
            stmt = stmt.where(StudyPreset.id != except_id)
        await self._db.execute(stmt.values(is_default=False))

    async def create(self, user: User, body: PresetIn) -> StudyPreset:
        count = (
            await self._db.execute(
                select(func.count(StudyPreset.id)).where(StudyPreset.user_id == user.id)
            )
        ).scalar_one()
        if count >= MAX_PRESETS:
            raise PresetLimitError()
        row = StudyPreset(user_id=user.id, **body.model_dump(exclude={"is_default"}))
        try:
            if body.is_default:
                await self._clear_default(user.id, None)
            row.is_default = body.is_default
            self._db.add(row)
            await self._db.commit()
        except IntegrityError:
            await self._db.rollback()
            raise PresetNameTakenError() from None
        await self._db.refresh(row)
        return row

    async def replace(self, user: User, preset_id: uuid.UUID, body: PresetIn) -> StudyPreset:
        row = await self.get_owned(user.id, preset_id)
        try:
            if body.is_default:
                await self._clear_default(user.id, row.id)
            for name, value in body.model_dump().items():
                setattr(row, name, value)
            await self._db.commit()
        except IntegrityError:
            await self._db.rollback()
            raise PresetNameTakenError() from None
        await self._db.refresh(row)
        return row

    async def set_default(self, user: User, preset_id: uuid.UUID, value: bool) -> StudyPreset:
        row = await self.get_owned(user.id, preset_id)
        if value:
            await self._clear_default(user.id, row.id)
        row.is_default = value
        await self._db.commit()
        await self._db.refresh(row)
        return row

    async def delete(self, user: User, preset_id: uuid.UUID) -> None:
        row = await self.get_owned(user.id, preset_id)
        await self._db.delete(row)
        await self._db.commit()
