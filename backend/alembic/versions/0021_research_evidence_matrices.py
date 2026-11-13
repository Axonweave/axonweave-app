"""research evidence matrices (Phase 7 M7.5)

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid(name: str, nullable: bool = False) -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=nullable)


def _ts(name: str) -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "research_evidence_matrices",
        _uuid("id"),
        _uuid("user_id"),
        _uuid("research_project_id"),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["research_project_id", "user_id"],
            ["research_projects.id", "research_projects.user_id"],
            name="fk_research_matrices_project_owner",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("id", "user_id", name="uq_research_matrices_id_user"),
    )
    op.create_index(
        "ix_research_matrices_project",
        "research_evidence_matrices",
        ["user_id", "research_project_id"],
    )
    op.create_table(
        "research_evidence_matrix_columns",
        _uuid("id"),
        _uuid("user_id"),
        _uuid("matrix_id"),
        sa.Column("column_key", sa.String(60), nullable=False),
        sa.Column("title", sa.String(80), nullable=False),
        sa.Column("data_type", sa.String(12), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(60), nullable=True),
        sa.Column("configuration", postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["matrix_id", "user_id"],
            ["research_evidence_matrices.id", "research_evidence_matrices.user_id"],
            name="fk_research_matrix_columns_matrix_owner",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("id", "matrix_id", name="uq_research_matrix_columns_id_matrix"),
        sa.UniqueConstraint("matrix_id", "column_key", name="uq_research_matrix_columns_key"),
    )
    op.create_index(
        "ix_research_matrix_columns_matrix",
        "research_evidence_matrix_columns",
        ["matrix_id", "position"],
    )
    op.create_table(
        "research_evidence_matrix_entries",
        _uuid("id"),
        _uuid("user_id"),
        _uuid("matrix_id"),
        _uuid("research_paper_id"),
        _uuid("column_id"),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("value_origin", sa.String(14), nullable=False),
        sa.Column("evidence_ids", postgresql.JSONB(), nullable=False),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["matrix_id", "user_id"],
            ["research_evidence_matrices.id", "research_evidence_matrices.user_id"],
            name="fk_research_matrix_entries_matrix_owner",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["research_paper_id", "user_id"],
            ["research_papers.id", "research_papers.user_id"],
            name="fk_research_matrix_entries_paper_owner",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["column_id", "matrix_id"],
            ["research_evidence_matrix_columns.id", "research_evidence_matrix_columns.matrix_id"],
            name="fk_research_matrix_entries_column",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("matrix_id", "research_paper_id", "column_id", name="uq_research_cell"),
        sa.CheckConstraint(
            "value_origin IN ('extracted', 'ai_generated', 'researcher')",
            name="ck_research_matrix_entries_origin",
        ),
    )


def downgrade() -> None:
    op.drop_table("research_evidence_matrix_entries")
    op.drop_table("research_evidence_matrix_columns")
    op.drop_table("research_evidence_matrices")
