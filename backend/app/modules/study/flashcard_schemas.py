"""Flashcard API schemas (spec 6.4, 19.3). Responses carry card text and source references (ids and
locations), never prompts, provider text or source passages."""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.study.generators.flashcards import MAX_BACK, MAX_CARDS, MAX_EXPLANATION, MAX_FRONT

CardType = Literal[
    "basic", "definition", "concept", "comparison", "fill_in_the_blank", "application"
]
Difficulty = Literal["easy", "medium", "hard"]
Front = Annotated[str, Field(min_length=5, max_length=MAX_FRONT)]
Back = Annotated[str, Field(min_length=1, max_length=MAX_BACK)]
Explanation = Annotated[str, Field(max_length=MAX_EXPLANATION)]


class FlashcardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    front: str
    back: str
    explanation: str | None
    card_type: CardType
    difficulty: Difficulty
    source_references: list[dict[str, Any]]
    display_order: int
    is_favourite: bool
    origin: Literal["generated", "manual"]
    revision: int
    created_at: datetime
    updated_at: datetime


class FlashcardSetOut(BaseModel):
    id: uuid.UUID
    study_material_id: uuid.UUID
    workspace_id: uuid.UUID
    subject_id: uuid.UUID | None
    chapter_id: uuid.UUID | None
    title: str
    generation_settings: dict[str, Any]
    card_count: int
    cards: list[FlashcardOut]
    created_at: datetime
    updated_at: datetime


class FlashcardSetResponse(BaseModel):
    success: bool = True
    data: FlashcardSetOut


class FlashcardResponse(BaseModel):
    success: bool = True
    data: FlashcardOut


class FlashcardListResponse(BaseModel):
    success: bool = True
    data: list[FlashcardOut]


class AddCardRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    front: Front
    back: Back
    explanation: Explanation | None = None
    card_type: CardType = "basic"
    difficulty: Difficulty = "medium"


class EditCardRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    front: Front | None = None
    back: Back | None = None
    explanation: Explanation | None = None
    card_type: CardType | None = None
    difficulty: Difficulty | None = None
    is_favourite: bool | None = None

    @model_validator(mode="after")
    def _something(self) -> "EditCardRequest":
        if not self.model_fields_set:
            raise ValueError("no changes given")
        for required in ("front", "back", "card_type", "difficulty", "is_favourite"):
            if required in self.model_fields_set and getattr(self, required) is None:
                raise ValueError(f"{required} cannot be null")
        return self


class ReorderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    card_ids: list[uuid.UUID] = Field(min_length=1, max_length=200)


class RegenerateCardsRequest(BaseModel):
    """Regenerate the selected cards as a preview; nothing changes until the preview is applied."""

    model_config = ConfigDict(extra="forbid")

    card_ids: list[uuid.UUID] = Field(min_length=1, max_length=MAX_CARDS)
    settings: dict[str, Any] | None = None
