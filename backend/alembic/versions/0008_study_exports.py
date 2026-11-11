"""study exports (Phase 4 M5)

Creates `study_exports` (spec 14, 19.5): one row per export request, the finished file lives in
private object storage and is served through a short-lived, ownership-checked download (D-100).

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-11

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _ts(name: str) -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "study_exports",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("study_material_id", sa.UUID(), nullable=False),
        sa.Column("export_format", sa.String(8), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("storage_key", sa.String(300), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(48), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["study_material_id", "user_id"],
            ["study_materials.id", "study_materials.user_id"],
            ondelete="CASCADE",
            name="fk_study_exports_material_owner",
        ),
        sa.CheckConstraint(
            "export_format IN ('pdf', 'csv', 'md', 'docx')", name="ck_study_exports_format"
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'completed', 'failed', 'expired')",
            name="ck_study_exports_status",
        ),
    )
    op.create_index(op.f("ix_study_exports_id"), "study_exports", ["id"])
    op.create_index("ix_study_exports_user_created", "study_exports", ["user_id", "created_at"])
    op.create_index("ix_study_exports_material", "study_exports", ["study_material_id"])
    op.create_index("ix_study_exports_status_expires", "study_exports", ["status", "expires_at"])
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'axonweave_app') THEN "
        "GRANT SELECT, INSERT, UPDATE, DELETE ON study_exports TO axonweave_app; END IF; END $$"
    )


def downgrade() -> None:
    op.drop_table("study_exports")
