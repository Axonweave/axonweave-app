import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.activity_log import ActivityLog
    from app.models.subject import Subject
    from app.models.user import User


class Workspace(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "workspaces"
    __table_args__ = (
        # Target for composite ownership FKs (documents, Phase 3).
        UniqueConstraint("id", "user_id", name="uq_workspaces_id_user"),
        # D-11: unique name per user among non-archived rows (case-insensitive)
        Index(
            "ix_workspaces_user_name_unique",
            "user_id",
            text("lower(name)"),
            unique=True,
            postgresql_where="archived_at IS NULL",
        ),
        # D-13: exactly one default workspace per user
        Index(
            "ix_workspaces_user_default_unique",
            "user_id",
            unique=True,
            postgresql_where="is_default = true",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    workspace_type: Mapped[str] = mapped_column(
        String(64), nullable=False, default="personal_learning"
    )
    icon: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # D-01: colour field added
    colour: Mapped[str | None] = mapped_column(String(16), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="workspaces")
    subjects: Mapped[list["Subject"]] = relationship(
        "Subject", back_populates="workspace", cascade="all, delete-orphan"
    )
    activity_logs: Mapped[list["ActivityLog"]] = relationship(
        "ActivityLog", back_populates="workspace"
    )
