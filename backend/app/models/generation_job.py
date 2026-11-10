import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.database.fk import SetNullColumnsFK

JOB_STATUSES = (
    "pending",
    "retrieving_sources",
    "generating",
    "validating",
    "saving",
    "completed",
    "failed",
    "cancelled",
)
ACTIVE_STATUSES = ("pending", "retrieving_sources", "generating", "validating", "saving")
_STATUS_SQL = ", ".join(f"'{s}'" for s in JOB_STATUSES)
_ACTIVE_SQL = ", ".join(f"'{s}'" for s in ACTIVE_STATUSES)


class GenerationJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One generation run (spec 18.3). The id is the generation id.

    `request` holds the validated source selection and settings (ids and options, never document
    text). The partial unique index on the request fingerprint lets only one *active* job exist per
    identical request: a double click or a retry returns the running job (D-87).
    """

    __tablename__ = "generation_jobs"
    __table_args__ = (
        SetNullColumnsFK(
            ["study_material_id", "user_id"],
            ["study_materials.id", "study_materials.user_id"],
            set_null=["study_material_id"],
            name="fk_generation_jobs_material_owner",
        ),
        CheckConstraint(f"status IN ({_STATUS_SQL})", name="ck_generation_jobs_status"),
        CheckConstraint("progress >= 0 AND progress <= 100", name="ck_generation_jobs_progress"),
        CheckConstraint("provider_calls >= 0", name="ck_generation_jobs_provider_calls"),
        Index(
            "uq_generation_jobs_active_fingerprint",
            "user_id",
            "fingerprint",
            unique=True,
            postgresql_where=text(f"status IN ({_ACTIVE_SQL})"),
        ),
        Index("ix_generation_jobs_user_created", "user_id", "created_at"),
        Index("ix_generation_jobs_user_status", "user_id", "status"),
        Index("ix_generation_jobs_status_heartbeat", "status", "heartbeat_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    study_material_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    generation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="pending", server_default=text("'pending'")
    )
    progress: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    model_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)  # safe code only
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    request: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source_stats: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # Result of a regeneration, held for review until the user applies or discards it (D-92).
    preview: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    provider_calls: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    cancel_requested: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    celery_task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
