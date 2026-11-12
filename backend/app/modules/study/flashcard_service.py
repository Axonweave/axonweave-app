"""Flashcard service (spec 6.6, 19.3): read a deck, add / edit / delete / reorder cards, and
regenerate selected cards as a PREVIEW.

Rules: ownership is checked first on every path (a foreign id is a 404 exactly like a missing one);
regeneration never touches a card until the user applies the preview, and applying refuses (409)
when any selected card was edited, deleted or reordered away since the preview was made, so user
edits are never overwritten (spec 6.6, D-93).
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.flashcard import Flashcard, FlashcardSet
from app.models.generation_job import GenerationJob
from app.models.study_material import StudyMaterial
from app.models.user import User
from app.modules.study.service import StudyGenerationService
from app.repositories.flashcard_repository import FlashcardRepository
from app.repositories.generation_job_repository import GenerationJobRepository
from app.repositories.study_material_repository import StudyMaterialRepository
from app.study.errors import (
    DuplicateFlashcardError,
    FlashcardLimitError,
    FlashcardNotFoundError,
    GenerationNotFoundError,
    InvalidEditError,
    MaterialNotFoundError,
    PreviewNotAvailableError,
    PreviewStaleError,
    RegenerationNotPossibleError,
)
from app.study.flashcard_rows import generated_card_rows
from app.study.generators.base import OutputInvalid
from app.study.generators.flashcards import CardOut, card_rules
from app.study.generators.registry import get_generator, validate_settings
from app.study.schemas import GenerationRequest, SourceSpec, clean_text
from app.study.validation import describe_errors, is_near_duplicate

MAX_CARDS_PER_SET = 200
MAX_REGENERATE_CARDS = 30
_EDITABLE = ("front", "back", "explanation", "card_type", "difficulty")


def _check(front: str, back: str, explanation: str | None, card_type: str, difficulty: str) -> None:
    try:
        card = CardOut(
            front=front,
            back=back,
            explanation=explanation or "",
            card_type=card_type,  # type: ignore[arg-type]
            difficulty=difficulty,  # type: ignore[arg-type]
        )
        card_rules(0, card)
    except ValidationError as exc:
        raise InvalidEditError(describe_errors(exc)) from None
    except OutputInvalid as bad:
        raise InvalidEditError(str(bad)[:200]) from None


def _is_duplicate(front: str, back: str, others: list[Flashcard]) -> bool:
    return any(
        is_near_duplicate(front, o.front)
        or is_near_duplicate(f"{front} {back}", f"{o.front} {o.back}")
        for o in others
    )


class FlashcardService:
    def __init__(
        self, db: AsyncSession, settings: Settings, generations: StudyGenerationService
    ) -> None:
        self._db = db
        self._s = settings
        self._gen = generations
        self._cards = FlashcardRepository(db)
        self._materials = StudyMaterialRepository(db)
        self._jobs = GenerationJobRepository(db)

    # reads ───────────────────────────────────────────────────────────────────

    async def _owned_set(self, user: User, set_id: uuid.UUID) -> FlashcardSet:
        card_set = await self._cards.get_set(set_id, user.id)
        if card_set is None:
            raise MaterialNotFoundError
        return card_set

    async def _owned_card(self, user: User, card_id: uuid.UUID) -> Flashcard:
        card = await self._cards.get_card(card_id, user.id)
        if card is None:
            raise FlashcardNotFoundError
        return card

    async def _material(self, user: User, card_set: FlashcardSet) -> StudyMaterial:
        material = await self._materials.get_owned(card_set.study_material_id, user.id)
        if material is None:
            raise MaterialNotFoundError
        return material

    async def get(
        self, user: User, set_id: uuid.UUID
    ) -> tuple[FlashcardSet, StudyMaterial, list[Flashcard]]:
        card_set = await self._owned_set(user, set_id)
        material = await self._material(user, card_set)
        return card_set, material, await self._cards.cards(card_set.id, user.id)

    # edits ───────────────────────────────────────────────────────────────────

    async def add_card(self, user: User, set_id: uuid.UUID, data: dict[str, Any]) -> Flashcard:
        card_set = await self._owned_set(user, set_id)
        existing = await self._cards.cards(card_set.id, user.id)
        if len(existing) >= MAX_CARDS_PER_SET:
            raise FlashcardLimitError
        front, back = clean_text(data["front"]), clean_text(data["back"])
        explanation = clean_text(data["explanation"]) if data.get("explanation") else None
        _check(front, back, explanation, data["card_type"], data["difficulty"])
        if _is_duplicate(front, back, existing):
            raise DuplicateFlashcardError
        order = await self._cards.next_order(card_set.id, user.id)
        (card,) = await self._cards.add_cards(
            card_set,
            [
                {
                    "front": front,
                    "back": back,
                    "explanation": explanation,
                    "card_type": data["card_type"],
                    "difficulty": data["difficulty"],
                    "source_references": [],
                    "origin": "manual",
                }
            ],
            order,
        )
        await self._cards.touch_set(card_set.id, user.id)
        await self._db.commit()
        return card

    async def edit_card(self, user: User, card_id: uuid.UUID, changes: dict[str, Any]) -> Flashcard:
        card = await self._owned_card(user, card_id)
        set_id = card.flashcard_set_id
        merged: dict[str, Any] = {k: getattr(card, k) for k in _EDITABLE}
        content_changed = False
        for key in _EDITABLE:
            if key not in changes:
                continue
            value = changes[key]
            if key in ("front", "back"):
                value = clean_text(value)
            elif key == "explanation":
                value = clean_text(value) if value else None
            if value != merged[key]:
                content_changed = True
            merged[key] = value
        _check(
            merged["front"],
            merged["back"],
            merged["explanation"],
            merged["card_type"],
            merged["difficulty"],
        )
        if content_changed and ("front" in changes or "back" in changes):
            others = [c for c in await self._cards.cards(set_id, user.id) if c.id != card.id]
            if _is_duplicate(merged["front"], merged["back"], others):
                raise DuplicateFlashcardError
        for key, value in merged.items():
            setattr(card, key, value)
        if "is_favourite" in changes:
            card.is_favourite = bool(changes["is_favourite"])
        if content_changed:
            card.revision += 1
            await self._cards.touch_set(set_id, user.id)
        await self._db.commit()
        await self._db.refresh(card)
        return card

    async def delete_card(self, user: User, card_id: uuid.UUID) -> None:
        card = await self._owned_card(user, card_id)
        set_id = card.flashcard_set_id
        await self._cards.delete_card(card)
        await self._cards.touch_set(set_id, user.id)
        await self._db.commit()

    async def reorder(
        self, user: User, set_id: uuid.UUID, ordered_ids: list[uuid.UUID]
    ) -> list[Flashcard]:
        user_id = user.id  # read before commit expires the instance
        card_set = await self._owned_set(user, set_id)
        owned_set_id = card_set.id  # read before commit expires the instance
        existing = await self._cards.cards(owned_set_id, user_id)
        if len(set(ordered_ids)) != len(ordered_ids) or {c.id for c in existing} != set(
            ordered_ids
        ):
            raise InvalidEditError("card_ids: must list every card of the set exactly once")
        await self._cards.set_order(owned_set_id, user_id, ordered_ids)
        await self._cards.touch_set(owned_set_id, user_id)
        await self._db.commit()
        self._db.expire_all()
        return await self._cards.cards(owned_set_id, user_id)

    # regenerate selected cards (preview) ────────────────────────────────────

    async def regenerate(
        self,
        user: User,
        set_id: uuid.UUID,
        card_ids: list[uuid.UUID],
        settings: dict[str, Any] | None,
    ) -> tuple[GenerationJob, bool]:
        card_set = await self._owned_set(user, set_id)
        material = await self._material(user, card_set)
        ids = list(dict.fromkeys(card_ids))
        if not 1 <= len(ids) <= MAX_REGENERATE_CARDS:
            raise InvalidEditError("card_ids: select between 1 and 30 cards")
        selected = await self._cards.get_cards(card_set.id, user.id, ids)
        if len(selected) != len(ids):  # a card of another set or user is a 404
            raise FlashcardNotFoundError
        try:
            spec = SourceSpec.model_validate(material.source_metadata.get("source") or {})
        except ValidationError:  # a pasted-text source was never stored (D-82)
            raise RegenerationNotPossibleError from None
        generator = get_generator("flashcards", self._s)
        merged = {**material.generation_settings, **(settings or {}), "count": len(ids)}
        validate_settings(generator, merged)
        request = GenerationRequest(generation_type="flashcards", source=spec, settings=merged)
        revisions = {str(c.id): c.revision for c in selected}
        return await self._gen.create(
            user,
            request,
            regenerate={
                "material_id": str(material.id),
                "base_version": material.current_version,
                "section_index": None,
                "heading": None,
                "set_id": str(card_set.id),
                "card_ids": [str(i) for i in ids],
                "revisions": revisions,
            },
        )

    async def _preview_job(self, user: User, job_id: uuid.UUID) -> GenerationJob:
        job = await self._jobs.get_owned(job_id, user.id)
        if job is None:
            raise GenerationNotFoundError
        if job.preview is None or "card_ids" not in job.preview:
            raise PreviewNotAvailableError
        return job

    async def apply_regeneration(
        self, user: User, set_id: uuid.UUID, job_id: uuid.UUID
    ) -> list[Flashcard]:
        """Replace the selected cards, in place, with the previewed ones. A selected card that
        changed since the preview, or a replacement that duplicates a kept card, leaves that
        card exactly as the user has it."""
        user_id = user.id  # read before commit expires the instance
        card_set = await self._owned_set(user, set_id)
        owned_set_id = card_set.id
        job = await self._preview_job(user, job_id)
        preview = job.preview or {}
        if preview.get("set_id") != str(card_set.id):
            raise GenerationNotFoundError
        selected_ids = [uuid.UUID(i) for i in preview["card_ids"]]
        revisions: dict[str, int] = preview["revisions"]
        selected = {
            c.id: c for c in await self._cards.get_cards(card_set.id, user_id, selected_ids)
        }
        for cid in selected_ids:
            card = selected.get(cid)
            if card is None or card.revision != revisions.get(str(cid)):
                raise PreviewStaleError
        new_cards = preview["content"]["payload"]["cards"]
        sources = preview["content"].get("sources") or []
        rows = generated_card_rows([_Gen(c) for c in new_cards], sources)
        kept = [c for c in await self._cards.cards(card_set.id, user_id) if c.id not in selected]
        applied = 0
        for cid, row in zip(selected_ids, rows, strict=False):
            if _is_duplicate(row["front"], row["back"], kept):
                continue  # keep the user's current card
            card = selected[cid]
            for key in ("front", "back", "explanation", "card_type", "difficulty"):
                setattr(card, key, row[key])
            card.source_references = row["source_references"]
            card.origin = "generated"
            card.revision += 1
            kept.append(card)
            applied += 1
        job.preview = None  # consumed: applying twice is impossible
        await self._cards.touch_set(card_set.id, user_id)
        await self._db.commit()
        self._db.expire_all()
        return await self._cards.cards(owned_set_id, user_id)


class _Gen:
    """Adapter so stored preview JSON can share `generated_card_rows` with engine output."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.front = data["front"]
        self.back = data["back"]
        self.explanation = data.get("explanation") or ""
        self.card_type = data["card_type"]
        self.difficulty = data["difficulty"]
        self.topic = data.get("topic") or ""
        self.source_refs = data.get("source_refs") or []
