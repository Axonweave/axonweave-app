"""allow request_kind 'evaluation' in ai_usage_records (Phase 5 M1, D-112)

Descriptive and short-answer grading calls the provider layer and records one usage row per call.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-13

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_ai_usage_request_kind", "ai_usage_records", type_="check")
    op.create_check_constraint(
        "ck_ai_usage_request_kind",
        "ai_usage_records",
        "request_kind IN ('chat', 'embedding', 'generation', 'evaluation')",
    )


def downgrade() -> None:
    op.execute("DELETE FROM ai_usage_records WHERE request_kind = 'evaluation'")
    op.drop_constraint("ck_ai_usage_request_kind", "ai_usage_records", type_="check")
    op.create_check_constraint(
        "ck_ai_usage_request_kind",
        "ai_usage_records",
        "request_kind IN ('chat', 'embedding', 'generation')",
    )
