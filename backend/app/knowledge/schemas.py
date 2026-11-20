"""Structured output the model must produce (validated with Pydantic, never trusted: D-126).

Model-supplied numbers refer to the SOURCE markers of one call; `validation.verify` maps them back
to real chunks and checks every quote against the chunk text."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.knowledge import NODE_TYPES, QUOTE_MAX_CHARS, RELATIONSHIP_TYPES

NodeType = Literal[NODE_TYPES]  # type: ignore[valid-type]
RelationshipType = Literal[RELATIONSHIP_TYPES]  # type: ignore[valid-type]

MAX_CONCEPTS_PER_CALL = 100
MAX_RELATIONSHIPS_PER_CALL = 200
DIFFICULTIES = ("introductory", "intermediate", "advanced")


class EvidenceItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    source: int = Field(ge=1)
    quote: str = Field(min_length=3, max_length=QUOTE_MAX_CHARS + 100)


class ExtractedConcept(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=2, max_length=200)
    type: NodeType = "concept"
    description: str | None = Field(default=None, max_length=1000)
    definition: str | None = Field(default=None, max_length=2000)
    aliases: list[str] = Field(default_factory=list, max_length=8)
    difficulty: Literal["introductory", "intermediate", "advanced"] | None = None
    confidence: float = Field(default=0.5, ge=0, le=1)
    evidence: list[EvidenceItem] = Field(min_length=1, max_length=5)

    # A thorough reply often invents a label ("process", "organelle"). The item is still verified
    # against its quote, so a label outside the list becomes the generic one instead of failing the
    # whole batch (D-146).
    @field_validator("type", mode="before")
    @classmethod
    def _known_type(cls, value: Any) -> Any:
        text = str(value).strip().lower() if isinstance(value, str) else ""
        return text if text in NODE_TYPES else "concept"

    @field_validator("difficulty", mode="before")
    @classmethod
    def _known_difficulty(cls, value: Any) -> Any:
        text = str(value).strip().lower() if isinstance(value, str) else ""
        return text if text in DIFFICULTIES else None


class ExtractedRelationship(BaseModel):
    model_config = ConfigDict(extra="ignore")

    source: str = Field(min_length=2, max_length=200)
    target: str = Field(min_length=2, max_length=200)
    type: RelationshipType
    statement: Literal["stated", "inferred"] = "stated"
    description: str | None = Field(default=None, max_length=500)
    confidence: float = Field(default=0.5, ge=0, le=1)
    evidence: list[EvidenceItem] = Field(min_length=1, max_length=5)

    @field_validator("type", mode="before")
    @classmethod
    def _known_type(cls, value: Any) -> Any:
        text = str(value).strip().upper().replace(" ", "_") if isinstance(value, str) else ""
        return text if text in RELATIONSHIP_TYPES else "RELATED_TO"


class ExtractionOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    concepts: list[ExtractedConcept] = Field(default_factory=list, max_length=MAX_CONCEPTS_PER_CALL)
    relationships: list[ExtractedRelationship] = Field(
        default_factory=list, max_length=MAX_RELATIONSHIPS_PER_CALL
    )

    # More items than one reply may carry: keep the first ones rather than reject the whole reply.
    @field_validator("concepts", mode="before")
    @classmethod
    def _trim_concepts(cls, value: Any) -> Any:
        return value[:MAX_CONCEPTS_PER_CALL] if isinstance(value, list) else value

    @field_validator("relationships", mode="before")
    @classmethod
    def _trim_relationships(cls, value: Any) -> Any:
        return value[:MAX_RELATIONSHIPS_PER_CALL] if isinstance(value, list) else value
