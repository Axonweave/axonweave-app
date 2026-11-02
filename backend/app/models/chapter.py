import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.folder import Folder
    from app.models.subject import Subject


class Chapter(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "chapters"
    __table_args__ = (
        CheckConstraint(
            "status IN ('not_started', 'in_progress', 'completed')",
            name="ck_chapters_status",
        ),
        # D-09: ensure folder_id belongs to the same subject via composite FK
        ForeignKeyConstraint(
            ["folder_id", "subject_id"],
            ["folders.id", "folders.subject_id"],
            name="fk_chapters_folder_subject",
            ondelete="SET NULL",
        ),
        Index("ix_chapters_subject_id", "subject_id"),
        Index("ix_chapters_folder_id", "folder_id"),
    )

    subject_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("subjects.id", ondelete="CASCADE"),
        nullable=False,
    )
    # folder_id participates in composite FK above (cannot also have simple FK)
    folder_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_started")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    subject: Mapped["Subject"] = relationship("Subject", back_populates="chapters")
    folder: Mapped["Folder | None"] = relationship(
        "Folder",
        back_populates="chapters",
        foreign_keys=[folder_id],
    )
