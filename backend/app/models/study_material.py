import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.database.fk import SetNullColumnsFK

RESOURCE_TYPES = (
    "summary",
    "flashcards",
    "quiz",
    "study_guide",
    "glossary",
    "formula_sheet",
    "question_bank",
    "echo",  # engine proof generator (M0); refused in production by the registry
)
_RESOURCE_SQL = ", ".join(f"'{t}'" for t in RESOURCE_TYPES)


class StudyMaterial(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One generated study resource (spec 18.1), owned by one user.

    `content` holds the structured resource plus source *references* (document and chunk ids), never
    copies of the source text (D-82). The subject and chapter links are cleared, not cascaded, when
    the subject or chapter is deleted: generated material belongs to the user, not to the folder.
    """

    __tablename__ = "study_materials"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["workspaces.id", "workspaces.user_id"],
            ondelete="CASCADE",
            name="fk_study_materials_workspace_owner",
        ),
        SetNullColumnsFK(
            ["subject_id", "workspace_id"],
            ["subjects.id", "subjects.workspace_id"],
            set_null=["subject_id"],
            name="fk_study_materials_subject_workspace",
        ),
        SetNullColumnsFK(
            ["chapter_id", "subject_id"],
            ["chapters.id", "chapters.subject_id"],
            set_null=["chapter_id"],
            name="fk_study_materials_chapter_subject",
        ),
        UniqueConstraint("id", "user_id", name="uq_study_materials_id_user"),
        CheckConstraint(f"resource_type IN ({_RESOURCE_SQL})", name="ck_study_materials_type"),
        CheckConstraint("status IN ('completed', 'failed')", name="ck_study_materials_status"),
        CheckConstraint("current_version >= 1", name="ck_study_materials_version"),
        Index("ix_study_materials_user_created", "user_id", "created_at"),
        Index("ix_study_materials_user_type", "user_id", "resource_type"),
        Index("ix_study_materials_workspace", "workspace_id"),
        Index("ix_study_materials_subject", "subject_id"),
        Index("ix_study_materials_chapter", "chapter_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    subject_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    chapter_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="completed", server_default=text("'completed'")
    )
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    generation_settings: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    current_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class StudyMaterialVersion(UUIDPrimaryKeyMixin, Base):
    """Immutable snapshot (spec 18.2). Version 1 is the original generated content (D-83)."""

    __tablename__ = "study_material_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["study_material_id", "user_id"],
            ["study_materials.id", "study_materials.user_id"],
            ondelete="CASCADE",
            name="fk_study_versions_material_owner",
        ),
        UniqueConstraint("study_material_id", "version_number", name="uq_study_versions_number"),
        CheckConstraint("version_number >= 1", name="ck_study_versions_number"),
        CheckConstraint(
            "origin IN ('generated', 'edited', 'restored', 'regenerated')",
            name="ck_study_versions_origin",
        ),
        Index("ix_study_versions_user", "user_id"),
    )

    study_material_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    origin: Mapped[str] = mapped_column(String(16), nullable=False, default="generated")
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    # NULL = created by the system (generation); otherwise the editing user.
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
