import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

EXPORT_FORMATS = ("pdf", "csv", "md", "docx")
_FORMAT_SQL = ", ".join(f"'{f}'" for f in EXPORT_FORMATS)


class StudyExport(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One export of one study material (spec 14, 19.5). The file lives in private object storage
    under a backend-generated key and is only ever served through an ownership-checked download
    before `expires_at` (D-100). Deleting the material deletes this row (its object goes through
    the storage cleanup outbox)."""

    __tablename__ = "study_exports"
    __table_args__ = (
        ForeignKeyConstraint(
            ["study_material_id", "user_id"],
            ["study_materials.id", "study_materials.user_id"],
            ondelete="CASCADE",
            name="fk_study_exports_material_owner",
        ),
        CheckConstraint(f"export_format IN ({_FORMAT_SQL})", name="ck_study_exports_format"),
        CheckConstraint(
            "status IN ('pending', 'completed', 'failed', 'expired')",
            name="ck_study_exports_status",
        ),
        Index("ix_study_exports_user_created", "user_id", "created_at"),
        Index("ix_study_exports_material", "study_material_id"),
        Index("ix_study_exports_status_expires", "status", "expires_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    study_material_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    export_format: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="pending")
    storage_key: Mapped[str | None] = mapped_column(String(300), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(48), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
