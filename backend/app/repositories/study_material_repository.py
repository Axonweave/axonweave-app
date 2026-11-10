"""Persistence for study materials and their version snapshots (always owner-scoped)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
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
