from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, UUIDPrimaryKeyMixin


class StorageCleanup(UUIDPrimaryKeyMixin, Base):
    """Outbox of storage objects to delete (D-66).

    Rows are written in the same transaction that deletes the document rows, and a Celery task
    deletes the objects and sets `done_at`. There is deliberately NO foreign key to users or
    documents: the rows must survive the cascade that removes them. The key is a backend-generated
    storage key (no user input) and is never returned by any API.
    """

    __tablename__ = "storage_cleanup"
    __table_args__ = (
        CheckConstraint("attempts >= 0", name="ck_storage_cleanup_attempts"),
        Index(
            "ix_storage_cleanup_pending",
            "next_attempt_at",
            postgresql_where=text("done_at IS NULL"),
        ),
    )

    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
