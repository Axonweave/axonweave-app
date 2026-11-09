import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

JOB_STATUSES = ("queued", "running", "succeeded", "failed", "cancelled")
_JOB_STATUS_SQL = ", ".join(f"'{s}'" for s in JOB_STATUSES)


class DocumentProcessingJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One processing run of one document version (D-68).

    The partial unique index lets only one job per version be `running`: a duplicate delivery or a
    double click cannot run two pipelines over the same version at once."""

    __tablename__ = "document_processing_jobs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["document_id", "user_id"],
            ["documents.id", "documents.user_id"],
            ondelete="CASCADE",
            name="fk_document_jobs_document_owner",
        ),
        ForeignKeyConstraint(
            ["document_version_id", "document_id"],
            ["document_versions.id", "document_versions.document_id"],
            ondelete="CASCADE",
            name="fk_document_jobs_version_document",
        ),
        CheckConstraint(f"status IN ({_JOB_STATUS_SQL})", name="ck_document_jobs_status"),
        CheckConstraint("retry_count >= 0", name="ck_document_jobs_retry_count"),
        Index(
            "uq_document_jobs_one_running_per_version",
            "document_version_id",
            unique=True,
            postgresql_where=text("status = 'running'"),
        ),
        Index("ix_document_jobs_version_created", "document_version_id", "created_at"),
        Index("ix_document_jobs_user_status", "user_id", "status"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    document_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    pipeline_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    stage: Mapped[str] = mapped_column(String(24), nullable=False, default="queued")
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)  # safe code only
    celery_task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
