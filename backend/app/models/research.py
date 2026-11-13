"""Research Studio tables (Phase 7). Milestone 7.1: research projects.

A project lives in one of the user's workspaces (composite foreign key, so a project can never point
at someone else's workspace). Later milestones hang papers, notes, matrices and drafts off the
`(id, user_id)` and `(id, workspace_id)` keys declared here."""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

PROJECT_STATUSES = ("planning", "active", "on_hold", "completed")
_STATUS_SQL = ", ".join(f"'{s}'" for s in PROJECT_STATUSES)


class ResearchProject(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "research_projects"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["workspaces.id", "workspaces.user_id"],
            ondelete="CASCADE",
            name="fk_research_projects_workspace_owner",
        ),
        UniqueConstraint("id", "user_id", name="uq_research_projects_id_user"),
        UniqueConstraint("id", "workspace_id", name="uq_research_projects_id_workspace"),
        CheckConstraint(f"status IN ({_STATUS_SQL})", name="ck_research_projects_status"),
        CheckConstraint(
            "target_date IS NULL OR start_date IS NULL OR target_date >= start_date",
            name="ck_research_projects_dates",
        ),
        Index("ix_research_projects_user_workspace", "user_id", "workspace_id"),
        Index("ix_research_projects_user_status", "user_id", "status"),
        Index("ix_research_projects_user_updated", "user_id", "updated_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    domain: Mapped[str | None] = mapped_column(String(120), nullable=True)
    research_problem: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Short ordered lists the user edits as a whole; no independent lifecycle (spec 23.3).
    objectives: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    research_questions: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    keywords: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="planning")
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
