"""generation job preview (Phase 4 M1)

Adds `generation_jobs.preview`: the result of a regenerate request, held for review until the user
applies it as a new material version (D-92). Existing grants on the table cover the new column.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-11

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "generation_jobs", sa.Column("preview", postgresql.JSONB(astext_type=sa.Text()))
    )


def downgrade() -> None:
    op.drop_column("generation_jobs", "preview")
