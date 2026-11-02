import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.chapter import Chapter
    from app.models.subject import Subject


class Folder(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "folders"
    __table_args__ = (
        # D-09: needed for composite FK from chapters
        UniqueConstraint("id", "subject_id", name="uq_folders_id_subject_id"),
        # D-11: unique folder name per parent (NULLs in parent_folder_id are treated as equal
        # by most DBs, so we use a partial index per NULL/non-NULL parent separately)
        Index(
            "ix_folders_parent_name_unique",
            "parent_folder_id",
            func.lower("name"),
            unique=True,
            postgresql_where="archived_at IS NULL AND parent_folder_id IS NOT NULL",
        ),
        Index(
            "ix_folders_root_name_unique",
            "subject_id",
            func.lower("name"),
            unique=True,
            postgresql_where="archived_at IS NULL AND parent_folder_id IS NULL",
        ),
    )

    subject_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("subjects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parent_folder_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("folders.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    subject: Mapped["Subject"] = relationship("Subject", back_populates="folders")
    parent: Mapped["Folder | None"] = relationship(
        "Folder", back_populates="children", remote_side="Folder.id"
    )
    children: Mapped[list["Folder"]] = relationship(
        "Folder", back_populates="parent", cascade="all, delete-orphan"
    )
    chapters: Mapped[list["Chapter"]] = relationship(
        "Chapter", back_populates="folder", foreign_keys="Chapter.folder_id"
    )
