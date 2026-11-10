"""Persistence for study materials and their version snapshots (always owner-scoped)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.study_material import StudyMaterial, StudyMaterialVersion


class StudyMaterialRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create_with_first_version(self, **fields: Any) -> StudyMaterial:
        """The material and its version 1 (the original generated content) in one flush."""
        material = StudyMaterial(**fields)
        self._db.add(material)
        await self._db.flush()
        self._db.add(
            StudyMaterialVersion(
                study_material_id=material.id,
                user_id=material.user_id,
                version_number=1,
                origin="generated",
                content=material.content,
                created_by=None,
            )
        )
        await self._db.flush()
        return material

    async def get_owned(self, material_id: uuid.UUID, user_id: uuid.UUID) -> StudyMaterial | None:
        return (
            await self._db.execute(
                select(StudyMaterial).where(
                    StudyMaterial.id == material_id, StudyMaterial.user_id == user_id
                )
            )
        ).scalar_one_or_none()

    async def versions(
        self, material_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[StudyMaterialVersion]:
        rows = await self._db.execute(
            select(StudyMaterialVersion)
            .where(
                StudyMaterialVersion.study_material_id == material_id,
                StudyMaterialVersion.user_id == user_id,
            )
            .order_by(StudyMaterialVersion.version_number)
        )
        return list(rows.scalars())

    async def get_version(
        self, material_id: uuid.UUID, user_id: uuid.UUID, number: int
    ) -> StudyMaterialVersion | None:
        return (
            await self._db.execute(
                select(StudyMaterialVersion).where(
                    StudyMaterialVersion.study_material_id == material_id,
                    StudyMaterialVersion.user_id == user_id,
                    StudyMaterialVersion.version_number == number,
                )
            )
        ).scalar_one_or_none()

    async def save_new_version(
        self,
        material_id: uuid.UUID,
        user_id: uuid.UUID,
        expected_version: int,
        *,
        title: str,
        content: dict[str, Any],
        origin: str,
        generation_settings: dict[str, Any] | None = None,
    ) -> int | None:
        """Atomically move the material to a new version, keeping every earlier one. Returns the
        new version number, or None when `expected_version` is no longer current (nothing is
        overwritten behind the user's back: spec 13.2, 13.3)."""
        values: dict[str, Any] = {
            "title": title[:300],
            "content": content,
            "current_version": expected_version + 1,
            "updated_at": func.now(),
        }
        if generation_settings is not None:
            values["generation_settings"] = generation_settings
        result = await self._db.execute(
            update(StudyMaterial)
            .where(
                StudyMaterial.id == material_id,
                StudyMaterial.user_id == user_id,
                StudyMaterial.current_version == expected_version,
            )
            .values(**values)
            .returning(StudyMaterial.id)
        )
        if result.scalar_one_or_none() is None:
            return None
        self._db.add(
            StudyMaterialVersion(
                study_material_id=material_id,
                user_id=user_id,
                version_number=expected_version + 1,
                origin=origin,
                content=content,
                created_by=user_id,
            )
        )
        await self._db.flush()
        return expected_version + 1
