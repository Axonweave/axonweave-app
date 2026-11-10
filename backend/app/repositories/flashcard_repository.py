"""Persistence for flashcard sets and cards. Every read and write is scoped by `user_id`."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.flashcard import Flashcard, FlashcardSet


class FlashcardRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create_set(self, user_id: uuid.UUID, material_id: uuid.UUID) -> FlashcardSet:
        card_set = FlashcardSet(user_id=user_id, study_material_id=material_id)
        self._db.add(card_set)
        await self._db.flush()
        return card_set

    async def add_cards(
        self, card_set: FlashcardSet, cards: Sequence[dict[str, Any]], start_order: int = 0
    ) -> list[Flashcard]:
        rows = [
            Flashcard(user_id=card_set.user_id, flashcard_set_id=card_set.id, display_order=i, **c)
            for i, c in enumerate(cards, start=start_order)
        ]
        self._db.add_all(rows)
        await self._db.flush()
        return rows

    async def get_set(self, set_id: uuid.UUID, user_id: uuid.UUID) -> FlashcardSet | None:
        return (
            await self._db.execute(
                select(FlashcardSet).where(
                    FlashcardSet.id == set_id, FlashcardSet.user_id == user_id
                )
            )
        ).scalar_one_or_none()

    async def get_set_for_material(
        self, material_id: uuid.UUID, user_id: uuid.UUID
    ) -> FlashcardSet | None:
        return (
            await self._db.execute(
                select(FlashcardSet).where(
                    FlashcardSet.study_material_id == material_id, FlashcardSet.user_id == user_id
                )
            )
        ).scalar_one_or_none()

    async def cards(self, set_id: uuid.UUID, user_id: uuid.UUID) -> list[Flashcard]:
        rows = await self._db.execute(
            select(Flashcard)
            .where(Flashcard.flashcard_set_id == set_id, Flashcard.user_id == user_id)
            .order_by(Flashcard.display_order, Flashcard.created_at, Flashcard.id)
        )
        return list(rows.scalars())

    async def get_card(self, card_id: uuid.UUID, user_id: uuid.UUID) -> Flashcard | None:
        return (
            await self._db.execute(
                select(Flashcard).where(Flashcard.id == card_id, Flashcard.user_id == user_id)
            )
        ).scalar_one_or_none()

    async def get_cards(
        self, set_id: uuid.UUID, user_id: uuid.UUID, ids: Sequence[uuid.UUID]
    ) -> list[Flashcard]:
        rows = await self._db.execute(
            select(Flashcard).where(
                Flashcard.flashcard_set_id == set_id,
                Flashcard.user_id == user_id,
                Flashcard.id.in_(ids),
            )
        )
        return list(rows.scalars())

    async def count(self, set_id: uuid.UUID, user_id: uuid.UUID) -> int:
        return int(
            (
                await self._db.execute(
                    select(func.count())
                    .select_from(Flashcard)
                    .where(Flashcard.flashcard_set_id == set_id, Flashcard.user_id == user_id)
                )
            ).scalar_one()
        )

    async def next_order(self, set_id: uuid.UUID, user_id: uuid.UUID) -> int:
        top = (
            await self._db.execute(
                select(func.max(Flashcard.display_order)).where(
                    Flashcard.flashcard_set_id == set_id, Flashcard.user_id == user_id
                )
            )
        ).scalar_one()
        return 0 if top is None else int(top) + 1

    async def delete_card(self, card: Flashcard) -> None:
        await self._db.execute(
            delete(Flashcard).where(Flashcard.id == card.id, Flashcard.user_id == card.user_id)
        )

    async def set_order(
        self, set_id: uuid.UUID, user_id: uuid.UUID, ordered_ids: Sequence[uuid.UUID]
    ) -> None:
        for position, card_id in enumerate(ordered_ids):
            await self._db.execute(
                update(Flashcard)
                .where(
                    Flashcard.id == card_id,
                    Flashcard.flashcard_set_id == set_id,
                    Flashcard.user_id == user_id,
                )
                .values(display_order=position)
            )

    async def touch_set(self, set_id: uuid.UUID, user_id: uuid.UUID) -> None:
        await self._db.execute(
            update(FlashcardSet)
            .where(FlashcardSet.id == set_id, FlashcardSet.user_id == user_id)
            .values(updated_at=func.now())
        )
