"""Flashcard generator (spec 6): six card types, quality rules, near-duplicate detection and a
source reference per card.

The cards are saved by the engine into `flashcard_sets` / `flashcards` (the live deck the user
edits); the material keeps the original generated snapshot as version 1 (D-93).
"""

from __future__ import annotations

from typing import Annotated, Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.ai.prompts import study as prompts
from app.study.generators.base import Generator, GeneratorSettings, OutputInvalid
from app.study.schemas import CleanStr
from app.study.validation import clean_refs, find_near_duplicates

CardType = Literal[
    "basic", "definition", "concept", "comparison", "fill_in_the_blank", "application"
]
Difficulty = Literal["easy", "medium", "hard"]
CardTypeChoice = Literal[
    "mixed", "basic", "definition", "concept", "comparison", "fill_in_the_blank", "application"
]
MAX_CARDS = 50
MAX_FRONT = 400
MAX_BACK = 1200
MAX_EXPLANATION = 1200
MAX_BLANK_ANSWER = 120
BLANK = "___"


class FlashcardSettings(GeneratorSettings):
    count: int = Field(default=10, ge=1, le=MAX_CARDS)
    card_type: CardTypeChoice = "mixed"
    difficulty: Literal["easy", "medium", "hard", "mixed"] = "mixed"
    include_examples: bool = False
    include_explanations: bool = True
    include_source_references: bool = True


class CardOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    front: Annotated[CleanStr, Field(min_length=5, max_length=MAX_FRONT)]
    back: Annotated[CleanStr, Field(min_length=1, max_length=MAX_BACK)]
    card_type: CardType
    difficulty: Difficulty
    explanation: Annotated[CleanStr, Field(max_length=MAX_EXPLANATION)] = ""
    source_refs: list[int] = Field(default_factory=list, max_length=20)


class FlashcardOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Annotated[CleanStr, Field(min_length=1, max_length=200)]
    cards: list[CardOut] = Field(min_length=1, max_length=MAX_CARDS)


_TYPE_TEXT = {
    "basic": "basic question-and-answer cards",
    "definition": "definition cards (front: the term to define; back: its definition)",
    "concept": "concept explanation cards (why or how something works)",
    "comparison": "comparison cards (front: differentiate two concepts; back: a short comparison)",
    "fill_in_the_blank": (
        f"fill-in-the-blank cards (front: one sentence with the missing term replaced by "
        f"{BLANK}; back: ONLY the missing term or phrase)"
    ),
    "application": "application cards (front: a situation; back: how the concept applies)",
}
_SHAPE = (
    'Return JSON: {"title": string, "cards": [{"front": string, "back": string, "card_type": '
    '"basic" | "definition" | "concept" | "comparison" | "fill_in_the_blank" | "application", '
    '"difficulty": "easy" | "medium" | "hard", "explanation": string, "source_refs": [integer]}]}'
)


def _checked(settings: GeneratorSettings) -> FlashcardSettings:
    assert isinstance(settings, FlashcardSettings)
    return settings


def card_rules(i: int, card: CardOut) -> None:
    """Quality rules that hold for every card, generated or typed by the user."""
    if card.back.strip().casefold() == card.front.strip().casefold():
        raise OutputInvalid(f"cards.{i}: front and back are identical")
    if card.card_type == "fill_in_the_blank":
        if BLANK not in card.front:
            raise OutputInvalid(f"cards.{i}: fill-in-the-blank front has no blank")
        if len(card.back) > MAX_BLANK_ANSWER:
            raise OutputInvalid(f"cards.{i}: fill-in-the-blank answer too long")


class FlashcardGenerator(Generator):
    key = "flashcards"
    resource_type = "flashcards"
    prompt_key = prompts.FLASHCARDS_KEY
    settings_model = FlashcardSettings
    output_model = FlashcardOutput
    source_mode = "ordered"
    allow_sampled_fallback = True
    min_source_tokens = 20
    max_output_tokens: ClassVar[int | None] = 8000
    #: The live cards are rows in `flashcards`, edited through the flashcard endpoints (not by
    #: patching the material payload).
    item_store = True

    def instruction(self, settings: GeneratorSettings) -> str:
        s = _checked(settings)
        kinds = (
            "a mix of card types (basic, definition, concept, comparison, fill_in_the_blank, "
            "application) chosen to suit the material"
            if s.card_type == "mixed"
            else _TYPE_TEXT[s.card_type]
        )
        level = "a mix of easy, medium and hard" if s.difficulty == "mixed" else s.difficulty
        return (
            f"TASK\nWrite at most {s.count} flashcards, in {s.language}: {kinds}. Difficulty: "
            f"{level}. Keep each answer short.\n"
            + (
                "Add a short 'explanation' per card taken from the material.\n"
                if s.include_explanations
                else "Leave 'explanation' empty.\n"
            )
            + (
                "Where the material has an example, use it in the explanation.\n"
                if s.include_examples
                else ""
            )
            + _SHAPE
        )

    def title(self, output: Any, settings: GeneratorSettings) -> str:
        return str(output.title)

    def finalize(self, output: Any, source_count: int, settings: GeneratorSettings) -> Any:
        s = _checked(settings)
        if len(output.cards) > s.count:
            raise OutputInvalid("cards: more cards than requested")
        kept: list[CardOut] = []
        for i, card in enumerate(output.cards):
            card_rules(i, card)
            if s.card_type != "mixed" and card.card_type != s.card_type:
                raise OutputInvalid(f"cards.{i}: wrong card type")
            if s.difficulty != "mixed" and card.difficulty != s.difficulty:
                raise OutputInvalid(f"cards.{i}: wrong difficulty")
            card.source_refs = clean_refs(card.source_refs, source_count)
            if not s.include_explanations:
                card.explanation = ""
            if s.include_source_references and not card.source_refs:
                continue  # cannot be tied to the material: unsupported, so not kept
            if not s.include_source_references:
                card.source_refs = []
            kept.append(card)
        if not kept:
            raise OutputInvalid("cards: no card is supported by a source")
        if find_near_duplicates([f"{c.front} {c.back}" for c in kept]) or find_near_duplicates(
            [c.front for c in kept]
        ):
            raise OutputInvalid("cards: duplicate or near-duplicate cards")
        output.cards = kept
        return output

    def item_count(self, output: Any) -> int:
        return len(output.cards)
