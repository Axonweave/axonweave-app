import uuid
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

CARD_TYPES = ("basic", "definition", "concept", "comparison", "fill_in_the_blank", "application")
DIFFICULTIES = ("easy", "medium", "hard")
_CARD_SQL = ", ".join(f"'{t}'" for t in CARD_TYPES)
_DIFF_SQL = ", ".join(f"'{t}'" for t in DIFFICULTIES)


class FlashcardSet(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The live, editable deck of one flashcard study material (spec 18.4). The material keeps the
    original generated snapshot (version 1); this set and its cards are what the user edits."""

    __tablename__ = "flashcard_sets"
    __table_args__ = (
        ForeignKeyConstraint(
            ["study_material_id", "user_id"],
            ["study_materials.id", "study_materials.user_id"],
            ondelete="CASCADE",
            name="fk_flashcard_sets_material_owner",
        ),
        UniqueConstraint("study_material_id", name="uq_flashcard_sets_material"),
        UniqueConstraint("id", "user_id", name="uq_flashcard_sets_id_user"),
        Index("ix_flashcard_sets_user", "user_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    study_material_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)


class Flashcard(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One card (spec 18.5). `source_references` holds ids and locations only, never text (D-82).
    `revision` counts user edits so a regeneration preview can refuse to overwrite them."""

    __tablename__ = "flashcards"
    __table_args__ = (
        ForeignKeyConstraint(
            ["flashcard_set_id", "user_id"],
            ["flashcard_sets.id", "flashcard_sets.user_id"],
            ondelete="CASCADE",
            name="fk_flashcards_set_owner",
        ),
        CheckConstraint(f"card_type IN ({_CARD_SQL})", name="ck_flashcards_type"),
        CheckConstraint(f"difficulty IN ({_DIFF_SQL})", name="ck_flashcards_difficulty"),
        CheckConstraint("origin IN ('generated', 'manual')", name="ck_flashcards_origin"),
        CheckConstraint("display_order >= 0", name="ck_flashcards_order"),
        Index("ix_flashcards_set_order", "flashcard_set_id", "display_order"),
        Index("ix_flashcards_user", "user_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    flashcard_set_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    front: Mapped[str] = mapped_column(Text, nullable=False)
    back: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    card_type: Mapped[str] = mapped_column(String(24), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(8), nullable=False)
    source_references: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)
    is_favourite: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    origin: Mapped[str] = mapped_column(
        String(10), nullable=False, default="generated", server_default=text("'generated'")
    )
    revision: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
