from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PromptTemplate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A versioned system prompt. Immutable once synced; a change is a new version (D-41)."""

    __tablename__ = "prompt_templates"
    __table_args__ = (
        UniqueConstraint("prompt_key", "version", name="uq_prompt_templates_key_version"),
        CheckConstraint("version > 0", name="ck_prompt_templates_version"),
        Index(
            "uq_prompt_templates_one_active",
            "prompt_key",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )

    prompt_key: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
