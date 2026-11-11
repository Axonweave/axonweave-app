"""Study generation preferences (spec 16, D-89): user-set defaults, nothing inferred.

They are only DEFAULTS: a value the request sets explicitly always wins, and a default is applied
only where the chosen generator has a matching setting (and the value is valid for it).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.study_preferences import StudyGenerationPreferences
from app.models.user import User
from app.study.generators.base import Generator

_LENGTH_TO_DETAIL = {"short": "brief", "medium": "standard", "long": "detailed"}


class PreferencesIn(BaseModel):
    """Replaces the stored preferences; a field left out (or null) is cleared."""

    model_config = ConfigDict(extra="forbid")

    language: str | None = Field(
        default=None, min_length=2, max_length=32, pattern=r"^[A-Za-z][A-Za-z \-]*$"
    )
    explanation_level: Literal["beginner", "intermediate", "advanced"] | None = None
    summary_length: Literal["short", "medium", "long"] | None = None
    question_difficulty: Literal["easy", "medium", "hard", "mixed"] | None = None
    include_examples: bool = True
    include_definitions: bool = True
    include_source_references: bool = True


class PreferencesOut(PreferencesIn):
    pass


class PreferencesResponse(BaseModel):
    success: bool = True
    data: PreferencesOut


def _out(row: StudyGenerationPreferences | None) -> PreferencesOut:
    if row is None:
        return PreferencesOut()
    return PreferencesOut(
        language=row.language,
        explanation_level=row.explanation_level,  # type: ignore[arg-type]
        summary_length=row.summary_length,  # type: ignore[arg-type]
        question_difficulty=row.question_difficulty,  # type: ignore[arg-type]
        include_examples=row.include_examples,
        include_definitions=row.include_definitions,
        include_source_references=row.include_source_references,
    )


class StudyPreferencesService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def _row(self, user_id: object) -> StudyGenerationPreferences | None:
        return (
            await self._db.execute(
                select(StudyGenerationPreferences).where(
                    StudyGenerationPreferences.user_id == user_id
                )
            )
        ).scalar_one_or_none()

    async def get(self, user: User) -> PreferencesOut:
        return _out(await self._row(user.id))

    async def put(self, user: User, body: PreferencesIn) -> PreferencesOut:
        row = await self._row(user.id)
        if row is None:
            row = StudyGenerationPreferences(user_id=user.id)
            self._db.add(row)
        for name, value in body.model_dump().items():
            setattr(row, name, value)
        await self._db.commit()
        return _out(row)

    async def defaults_for(
        self, user_id: object, generator: Generator, requested: dict[str, Any]
    ) -> dict[str, Any]:
        """`requested` with the user's preferences filled in for settings the request left out."""
        row = await self._row(user_id)
        if row is None:
            return requested
        fields = generator.settings_model.model_fields
        wanted: dict[str, Any] = {
            "language": row.language,
            "level": row.explanation_level,
            "detail_level": _LENGTH_TO_DETAIL.get(row.summary_length or ""),
            "difficulty": row.question_difficulty,
            "include_examples": row.include_examples,
            "include_definitions": row.include_definitions,
            "include_source_references": row.include_source_references,
        }
        merged = dict(requested)
        for name, value in wanted.items():
            if value is None or name not in fields or name in requested:
                continue
            try:
                generator.settings_model.model_validate({**merged, name: value})
            except ValueError:
                continue  # not valid for this generator: keep its own default
            merged[name] = value
        return merged
