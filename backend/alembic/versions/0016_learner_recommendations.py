"""learner recommendations extend revision_recommendations (Phase 6 M6.8)

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_TYPES = "'quiz', 'flashcard', 'topic', 'chapter'"
NEW_TYPES = OLD_TYPES + (
    ", 'revise_concept', 'study_prerequisite', 'practise_concept', 'review_misconception', "
    "'review_due', 'assess_concept', 'study_related', 'revisit_chapter'"
)


def upgrade() -> None:
    op.alter_column(
        "revision_recommendations",
        "recommendation_type",
        existing_type=sa.String(length=12),
        type_=sa.String(length=24),
        existing_nullable=False,
    )
    op.add_column(
        "revision_recommendations",
        sa.Column(
            "source", sa.String(length=16), server_default=sa.text("'phase5_rule'"), nullable=False
        ),
    )
    op.add_column(
        "revision_recommendations", sa.Column("knowledge_node_id", sa.UUID(), nullable=True)
    )
    op.add_column(
        "revision_recommendations",
        sa.Column("suggested_action", sa.String(length=300), nullable=True),
    )
    op.add_column("revision_recommendations", sa.Column("score", sa.Numeric(6, 2), nullable=True))
    op.add_column(
        "revision_recommendations",
        sa.Column(
            "evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.drop_constraint(
        "ck_revision_recommendations_type", "revision_recommendations", type_="check"
    )
    op.create_check_constraint(
        "ck_revision_recommendations_type",
        "revision_recommendations",
        f"recommendation_type IN ({NEW_TYPES})",
    )
    op.create_check_constraint(
        "ck_revision_recommendations_source",
        "revision_recommendations",
        "source IN ('phase5_rule', 'learner_rule')",
    )
    # SET NULL on one column of a composite key (PostgreSQL 15+), as in app.database.fk
    op.execute(
        "ALTER TABLE revision_recommendations ADD CONSTRAINT fk_revision_recommendations_node_owner "
        "FOREIGN KEY (knowledge_node_id, user_id) REFERENCES knowledge_nodes (id, user_id) "
        "ON DELETE SET NULL (knowledge_node_id)"
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_revision_recommendations_node_owner", "revision_recommendations", type_="foreignkey"
    )
    op.execute("DELETE FROM revision_recommendations WHERE source = 'learner_rule'")
    op.drop_constraint(
        "ck_revision_recommendations_source", "revision_recommendations", type_="check"
    )
    op.drop_constraint(
        "ck_revision_recommendations_type", "revision_recommendations", type_="check"
    )
    op.create_check_constraint(
        "ck_revision_recommendations_type",
        "revision_recommendations",
        f"recommendation_type IN ({OLD_TYPES})",
    )
    for col in ("evidence", "score", "suggested_action", "knowledge_node_id", "source"):
        op.drop_column("revision_recommendations", col)
    op.alter_column(
        "revision_recommendations",
        "recommendation_type",
        existing_type=sa.String(length=24),
        type_=sa.String(length=12),
        existing_nullable=False,
    )
