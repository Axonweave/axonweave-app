"""research papers and duplicate reviews (Phase 7 M7.2)

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SOURCES = "'user_supplied', 'pdf_extracted', 'external_provider'"
STATUSES = "'unread', 'reading', 'read'"
ANALYSIS = "'not_analysed', 'queued', 'analysing', 'analysed', 'failed'"


def _list_col(name: str) -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(
        name, postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False
    )


def _uuid(name: str, nullable: bool = False) -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=nullable)


def upgrade() -> None:
    op.create_table(
        "research_papers",
        _uuid("id"),
        _uuid("user_id"),
        _uuid("research_project_id"),
        _uuid("document_id", nullable=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("title_normalised", sa.String(500), nullable=False),
        sa.Column("abstract", sa.Text(), nullable=True),
        _list_col("authors"),
        sa.Column("publication_year", sa.Integer(), nullable=True),
        sa.Column("venue", sa.String(300), nullable=True),
        sa.Column("publisher", sa.String(200), nullable=True),
        sa.Column("doi", sa.String(200), nullable=True),
        sa.Column("url", sa.String(1000), nullable=True),
        _list_col("keywords"),
        sa.Column("volume", sa.String(40), nullable=True),
        sa.Column("issue", sa.String(40), nullable=True),
        sa.Column("pages", sa.String(40), nullable=True),
        sa.Column("metadata_source", sa.String(24), nullable=False),
        sa.Column("metadata_verified", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("analysis_status", sa.String(24), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["research_project_id", "user_id"],
            ["research_projects.id", "research_projects.user_id"],
            ondelete="CASCADE",
            name="fk_research_papers_project_owner",
        ),
        sa.UniqueConstraint("id", "user_id", name="uq_research_papers_id_user"),
        sa.UniqueConstraint("id", "research_project_id", name="uq_research_papers_id_project"),
        sa.CheckConstraint(f"metadata_source IN ({SOURCES})", name="ck_research_papers_source"),
        sa.CheckConstraint(f"status IN ({STATUSES})", name="ck_research_papers_status"),
        sa.CheckConstraint(f"analysis_status IN ({ANALYSIS})", name="ck_research_papers_analysis"),
        sa.CheckConstraint(
            "publication_year IS NULL OR (publication_year >= 1000 AND publication_year <= 2200)",
            name="ck_research_papers_year",
        ),
    )
    # Only the document link is cleared when a document is deleted (never the owner column).
    op.execute(
        "ALTER TABLE research_papers ADD CONSTRAINT fk_research_papers_document_owner "
        "FOREIGN KEY (document_id, user_id) REFERENCES documents (id, user_id) "
        "ON DELETE SET NULL (document_id)"
    )
    op.create_index(
        "uq_research_papers_project_doi",
        "research_papers",
        ["research_project_id", "doi"],
        unique=True,
        postgresql_where=sa.text("doi IS NOT NULL"),
    )
    op.create_index(
        "uq_research_papers_project_document",
        "research_papers",
        ["research_project_id", "document_id"],
        unique=True,
        postgresql_where=sa.text("document_id IS NOT NULL"),
    )
    op.create_index(
        "ix_research_papers_user_project", "research_papers", ["user_id", "research_project_id"]
    )
    op.create_index(
        "ix_research_papers_project_title",
        "research_papers",
        ["research_project_id", "title_normalised"],
    )

    op.create_table(
        "research_paper_duplicate_reviews",
        _uuid("id"),
        _uuid("user_id"),
        _uuid("research_project_id"),
        _uuid("paper_a_id"),
        _uuid("paper_b_id"),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["paper_a_id", "user_id"],
            ["research_papers.id", "research_papers.user_id"],
            ondelete="CASCADE",
            name="fk_research_dup_a_owner",
        ),
        sa.ForeignKeyConstraint(
            ["paper_b_id", "user_id"],
            ["research_papers.id", "research_papers.user_id"],
            ondelete="CASCADE",
            name="fk_research_dup_b_owner",
        ),
        sa.UniqueConstraint("paper_a_id", "paper_b_id", name="uq_research_dup_pair"),
        sa.CheckConstraint("paper_a_id < paper_b_id", name="ck_research_dup_order"),
    )


def downgrade() -> None:
    op.drop_table("research_paper_duplicate_reviews")
    op.drop_table("research_papers")
