"""Study library: list, delete, duplicate, archive (spec 12, 19.2). Ownership first on every path:
a foreign id is a 404 exactly like a missing one."""

from __future__ import annotations

import copy
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.study_material import StudyMaterial
from app.models.user import User
from app.modules.documents.cleanup import enqueue_keys
from app.repositories.flashcard_repository import FlashcardRepository
from app.repositories.study_export_repository import StudyExportRepository
from app.repositories.study_material_repository import StudyMaterialRepository
from app.study.errors import DuplicateNotSupportedError, MaterialNotFoundError

DUPLICABLE = ("summary", "study_guide", "glossary", "formula_sheet", "flashcards")


def source_document_ids(material: StudyMaterial) -> list[uuid.UUID]:
    raw = material.source_metadata.get("documents") or []
    ids: list[uuid.UUID] = []
    for item in raw if isinstance(raw, list) else []:
        try:
            ids.append(uuid.UUID(str(item)))
        except ValueError:
            continue
    return ids


class StudyLibraryService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._materials = StudyMaterialRepository(db)

    async def _owned(self, user_id: uuid.UUID, material_id: uuid.UUID) -> StudyMaterial:
        material = await self._materials.get_owned(material_id, user_id)
        if material is None:
            raise MaterialNotFoundError
        return material

    async def unavailable_sources(
        self, user_id: uuid.UUID, materials: list[StudyMaterial]
    ) -> dict[uuid.UUID, list[uuid.UUID]]:
        """Per material, the source documents that no longer exist (deleted later)."""
        wanted = {d for m in materials for d in source_document_ids(m)}
        present = await self._materials.existing_document_ids(user_id, sorted(wanted, key=str))
        return {m.id: [d for d in source_document_ids(m) if d not in present] for m in materials}

    async def delete(self, user: User, material_id: uuid.UUID) -> None:
        user_id = user.id
        material = await self._owned(user_id, material_id)
        mid = material.id
        keys = await StudyExportRepository(self._db).keys_for_material(mid, user_id)
        await enqueue_keys(self._db, keys, "study_material_deleted")  # outbox first (D-66)
        await self._materials.delete(mid, user_id)  # versions, decks, quizzes, exports cascade
        await self._db.commit()

    async def set_archived(
        self, user: User, material_id: uuid.UUID, archived: bool
    ) -> StudyMaterial:
        user_id = user.id
        material = await self._owned(user_id, material_id)
        mid = material.id
        await self._materials.set_archived(mid, user_id, archived)
        await self._db.commit()
        await self._db.refresh(material)
        return material

    async def duplicate(self, user: User, material_id: uuid.UUID) -> StudyMaterial:
        user_id = user.id
        material = await self._owned(user_id, material_id)
        if material.resource_type not in DUPLICABLE or material.status != "completed":
            raise DuplicateNotSupportedError
        copy_row = await self._materials.create_with_first_version(
            user_id=user_id,
            workspace_id=material.workspace_id,
            subject_id=material.subject_id,
            chapter_id=material.chapter_id,
            title=f"{material.title[:290]} (copy)",
            resource_type=material.resource_type,
            status="completed",
            content=copy.deepcopy(material.content),
            generation_settings=copy.deepcopy(material.generation_settings),
            source_metadata=copy.deepcopy(material.source_metadata),
        )
        if material.resource_type == "flashcards":
            cards_repo = FlashcardRepository(self._db)
            source_set = await cards_repo.get_set_for_material(material.id, user_id)
            if source_set is not None:
                new_set = await cards_repo.create_set(user_id, copy_row.id)
                await cards_repo.add_cards(
                    new_set,
                    [
                        {
                            "front": c.front,
                            "back": c.back,
                            "explanation": c.explanation,
                            "card_type": c.card_type,
                            "difficulty": c.difficulty,
                            "source_references": copy.deepcopy(c.source_references),
                            "origin": c.origin,
                        }
                        for c in await cards_repo.cards(source_set.id, user_id)
                    ],
                )
        await self._db.commit()
        await self._db.refresh(copy_row)
        return copy_row
