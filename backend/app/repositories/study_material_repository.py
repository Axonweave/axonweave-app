"""Persistence for study materials and their version snapshots (always owner-scoped)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Text, cast, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.study_material import StudyMaterial, StudyMaterialVersion

_LIKE_ESCAPE = chr(92)


def _escape_like(value: str) -> str:
    """Escape LIKE wildcards so user text is matched literally (escape character: backslash)."""
    for ch in (_LIKE_ESCAPE, "%", "_"):
        value = value.replace(ch, _LIKE_ESCAPE + ch)
    return value


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

    # library (M5)

    async def list_library(
        self,
        user_id: uuid.UUID,
        *,
        q: str | None,
        resource_type: str | None,
        workspace_id: uuid.UUID | None,
        subject_id: uuid.UUID | None,
        chapter_id: uuid.UUID | None,
        status: str | None,
        archived: str,
        sort: str,
        descending: bool,
        limit: int,
        offset: int,
    ) -> tuple[list[StudyMaterial], int]:
        """Owner-scoped search, filters, allow-listed sort and pagination. `q` is a parameterised
        case-insensitive substring match on the title and the stored payload (wildcards escaped)."""
        conditions = [StudyMaterial.user_id == user_id]
        if q:
            escaped = _escape_like(q)
            pattern = f"%{escaped}%"
            conditions.append(
                or_(
                    StudyMaterial.title.ilike(pattern, escape=_LIKE_ESCAPE),
                    cast(StudyMaterial.content["payload"], Text).ilike(
                        pattern, escape=_LIKE_ESCAPE
                    ),
                )
            )
        if resource_type:
            conditions.append(StudyMaterial.resource_type == resource_type)
        if workspace_id:
            conditions.append(StudyMaterial.workspace_id == workspace_id)
        if subject_id:
            conditions.append(StudyMaterial.subject_id == subject_id)
        if chapter_id:
            conditions.append(StudyMaterial.chapter_id == chapter_id)
        if status:
            conditions.append(StudyMaterial.status == status)
        if archived == "no":
            conditions.append(StudyMaterial.archived_at.is_(None))
        elif archived == "only":
            conditions.append(StudyMaterial.archived_at.is_not(None))
        columns = {
            "created_at": StudyMaterial.created_at,
            "updated_at": StudyMaterial.updated_at,
            "title": StudyMaterial.title,
            "resource_type": StudyMaterial.resource_type,
        }
        column = columns[sort]
        order = column.desc() if descending else column.asc()
        total = (
            await self._db.execute(
                select(func.count()).select_from(StudyMaterial).where(*conditions)
            )
        ).scalar_one()
        rows = await self._db.execute(
            select(StudyMaterial)
            .where(*conditions)
            .order_by(order, StudyMaterial.id)
            .limit(limit)
            .offset(offset)
        )
        return list(rows.scalars()), int(total)

    async def delete(self, material_id: uuid.UUID, user_id: uuid.UUID) -> None:
        await self._db.execute(
            delete(StudyMaterial).where(
                StudyMaterial.id == material_id, StudyMaterial.user_id == user_id
            )
        )

    async def set_archived(
        self, material_id: uuid.UUID, user_id: uuid.UUID, archived: bool
    ) -> None:
        await self._db.execute(
            update(StudyMaterial)
            .where(StudyMaterial.id == material_id, StudyMaterial.user_id == user_id)
            .values(archived_at=func.now() if archived else None)
        )

    async def existing_document_ids(
        self, user_id: uuid.UUID, document_ids: list[uuid.UUID]
    ) -> set[uuid.UUID]:
        if not document_ids:
            return set()
        rows = await self._db.execute(
            select(Document.id).where(Document.user_id == user_id, Document.id.in_(document_ids))
        )
        return set(rows.scalars())
