"""Study material service: edit, versions, regenerate (preview) and apply.

Rules (spec 13, D-92): the original generated version is kept forever; every edit, restore or
applied
regeneration is a NEW version; a regeneration is only ever a preview until the user applies it, and
applying a preview made against an older version is refused (409) so edits are never overwritten.
Ownership is checked first on every path: a foreign id is a 404 exactly like a missing one.
"""

from __future__ import annotations

import copy
import uuid
from typing import Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.generation_job import GenerationJob
from app.models.study_material import StudyMaterial, StudyMaterialVersion
from app.models.user import User
from app.modules.study.service import StudyGenerationService
from app.repositories.generation_job_repository import GenerationJobRepository
from app.repositories.study_material_repository import StudyMaterialRepository
from app.study.errors import (
    GenerationNotFoundError,
    InvalidEditError,
    MaterialNotFoundError,
    MaterialVersionConflictError,
    PreviewNotAvailableError,
    PreviewStaleError,
    RegenerationNotPossibleError,
)
from app.study.generators.base import Generator, OutputInvalid
from app.study.generators.registry import generator_for_resource, validate_settings
from app.study.schemas import GenerationRequest, SourceSpec
from app.study.validation import describe_errors


class StudyMaterialService:
    def __init__(
        self, db: AsyncSession, settings: Settings, generations: StudyGenerationService
    ) -> None:
        self._db = db
        self._s = settings
        self._gen = generations
        self._materials = StudyMaterialRepository(db)
        self._jobs = GenerationJobRepository(db)

    # reads ───────────────────────────────────────────────────────────────────

    async def _owned(self, user: User, material_id: uuid.UUID) -> StudyMaterial:
        material = await self._materials.get_owned(material_id, user.id)
        if material is None:
            raise MaterialNotFoundError
        return material

    async def versions(self, user: User, material_id: uuid.UUID) -> list[StudyMaterialVersion]:
        await self._owned(user, material_id)
        return await self._materials.versions(material_id, user.id)

    async def version(
        self, user: User, material_id: uuid.UUID, number: int
    ) -> StudyMaterialVersion:
        await self._owned(user, material_id)
        found = await self._materials.get_version(material_id, user.id, number)
        if found is None:
            raise MaterialNotFoundError
        return found

    def _generator(self, material: StudyMaterial) -> Generator:
        generator = generator_for_resource(material.resource_type, self._s)
        if generator is None or generator.item_store:  # decks are edited card by card
            raise InvalidEditError
        return generator

    # edit / restore ──────────────────────────────────────────────────────────

    def _validated_payload(
        self, generator: Generator, payload: dict[str, Any], source_count: int
    ) -> tuple[dict[str, Any], str]:
        try:
            output = generator.output_model.model_validate(payload)
            output = generator.validate_edit(output, source_count)
        except ValidationError as exc:
            raise InvalidEditError(describe_errors(exc)) from None
        except OutputInvalid as bad:
            raise InvalidEditError(str(bad)[:300]) from None
        return generator.dump(output), str(output.title)

    async def edit(
        self, user: User, material_id: uuid.UUID, expected_version: int, payload: dict[str, Any]
    ) -> StudyMaterial:
        material = await self._owned(user, material_id)
        generator = self._generator(material)
        sources = material.content.get("sources") or []
        clean, title = self._validated_payload(generator, payload, len(sources))
        content = {**material.content, "payload": clean}
        return await self._save(user, material, expected_version, title, content, "edited", None)

    async def restore(
        self, user: User, material_id: uuid.UUID, expected_version: int, number: int
    ) -> StudyMaterial:
        """Copy an old version forward as a new one: history is never rewritten."""
        material = await self._owned(user, material_id)
        self._generator(material)
        old = await self._materials.get_version(material_id, user.id, number)
        if old is None:
            raise MaterialNotFoundError
        title = str(old.content.get("payload", {}).get("title") or material.title)
        return await self._save(
            user, material, expected_version, title, copy.deepcopy(old.content), "restored", None
        )

    async def _save(
        self,
        user: User,
        material: StudyMaterial,
        expected_version: int,
        title: str,
        content: dict[str, Any],
        origin: str,
        generation_settings: dict[str, Any] | None,
    ) -> StudyMaterial:
        material_id, user_id = material.id, user.id  # read before commit expires them
        saved = await self._materials.save_new_version(
            material_id,
            user_id,
            expected_version,
            title=title,
            content=content,
            origin=origin,
            generation_settings=generation_settings,
        )
        if saved is None:
            await self._db.rollback()
            raise MaterialVersionConflictError
        await self._db.commit()
        self._db.expire_all()
        fresh = await self._materials.get_owned(material_id, user_id)
        if fresh is None:
            raise MaterialNotFoundError
        return fresh

    # regenerate (preview) and apply ─────────────────────────────────────────

    async def regenerate(
        self,
        user: User,
        material_id: uuid.UUID,
        *,
        section_index: int | None,
        settings: dict[str, Any] | None,
    ) -> tuple[GenerationJob, bool]:
        material = await self._owned(user, material_id)
        generator = self._generator(material)
        try:
            spec = SourceSpec.model_validate(material.source_metadata.get("source") or {})
        except ValidationError:  # a pasted-text source was never stored (D-82)
            raise RegenerationNotPossibleError from None
        sections = material.content.get("payload", {}).get("sections") or []
        heading: str | None = None
        if section_index is not None:
            if not 0 <= section_index < len(sections):
                raise InvalidEditError
            heading = str(sections[section_index]["heading"])
        merged = {**material.generation_settings, **(settings or {})}
        validate_settings(generator, merged)
        request = GenerationRequest(generation_type=generator.key, source=spec, settings=merged)
        return await self._gen.create(
            user,
            request,
            regenerate={
                "material_id": str(material.id),
                "base_version": material.current_version,
                "section_index": section_index,
                "heading": heading,
            },
        )

    async def _preview_job(self, user: User, job_id: uuid.UUID) -> GenerationJob:
        job = await self._jobs.get_owned(job_id, user.id)
        if job is None:
            raise GenerationNotFoundError
        return job

    async def preview(self, user: User, job_id: uuid.UUID) -> tuple[dict[str, Any], int]:
        """The stored preview and the material's current version (differs from the preview's
        base version when it is already stale)."""
        job = await self._preview_job(user, job_id)
        if job.preview is None:
            raise PreviewNotAvailableError
        material = await self._materials.get_owned(uuid.UUID(job.preview["material_id"]), user.id)
        if material is None:
            raise MaterialNotFoundError
        return job.preview, material.current_version

    async def discard_preview(self, user: User, job_id: uuid.UUID) -> None:
        job = await self._preview_job(user, job_id)
        if job.preview is None:
            raise PreviewNotAvailableError
        job.preview = None
        await self._db.commit()

    async def apply_preview(self, user: User, job_id: uuid.UUID) -> StudyMaterial:
        job = await self._preview_job(user, job_id)
        preview = job.preview
        if preview is None or "card_ids" in preview:  # card previews: flashcard apply route
            raise PreviewNotAvailableError
        material = await self._owned(user, uuid.UUID(preview["material_id"]))
        if material.current_version != preview["base_version"]:
            raise PreviewStaleError
        generator = self._generator(material)
        new_content: dict[str, Any] = preview["content"]
        index = preview.get("section_index")
        if index is None:
            payload, title = new_content["payload"], str(new_content["payload"]["title"])
            content = {**material.content, **copy.deepcopy(new_content)}
            settings: dict[str, Any] | None = preview.get("settings")
        else:
            content, title = self._replace_section(material, new_content, int(index))
            payload = content["payload"]
            settings = None
        clean, title = self._validated_payload(generator, payload, len(content["sources"]))
        content["payload"] = clean
        job.preview = None  # consumed: applying twice is impossible
        return await self._save(
            user, material, int(preview["base_version"]), title, content, "regenerated", settings
        )

    @staticmethod
    def _replace_section(
        material: StudyMaterial, new_content: dict[str, Any], index: int
    ) -> tuple[dict[str, Any], str]:
        """Put the regenerated section in place; map its references onto the material's own source
        list by chunk id (appending sources the material did not yet cite)."""
        content = copy.deepcopy(material.content)
        sources: list[dict[str, Any]] = content["sources"]
        new_sources: list[dict[str, Any]] = new_content["sources"]
        section = copy.deepcopy(new_content["payload"]["sections"][0])
        mapped: list[int] = []
        for ref in section.get("source_refs", []):
            if not 1 <= ref <= len(new_sources):
                continue
            wanted = new_sources[ref - 1]
            rank = next(
                (
                    int(s["rank"])
                    for s in sources
                    if s.get("kind") == "chunk" and s.get("chunk_id") == wanted.get("chunk_id")
                ),
                None,
            )
            if rank is None:
                rank = len(sources) + 1
                sources.append({**wanted, "rank": rank})
            if rank not in mapped:
                mapped.append(rank)
        section["source_refs"] = mapped
        sections = content["payload"]["sections"]
        if not 0 <= index < len(sections):
            raise PreviewStaleError
        # Keep the heading the user sees if the model's collides with another section's.
        others = {s["heading"].casefold() for i, s in enumerate(sections) if i != index}
        if section["heading"].casefold() in others:
            section["heading"] = sections[index]["heading"]
        sections[index] = section
        return content, str(content["payload"]["title"])
