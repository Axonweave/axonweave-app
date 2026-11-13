"""web-grounded knowledge sources (Phase 6, D-144)

A knowledge run may now start from a subject name instead of a document, and its evidence is then a
website link rather than a document passage.

Revision ID: 0027
Revises: 0026
Create Date: 2026-11-14

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JOB_SOURCE = (
    "(source_kind = 'document' AND document_id IS NOT NULL) "
    "OR (source_kind = 'web' AND subject_id IS NOT NULL AND topic IS NOT NULL)"
)
_EVIDENCE_SOURCE = (
    "(source_kind = 'document' AND document_id IS NOT NULL "
    "AND document_version_id IS NOT NULL AND chunk_index IS NOT NULL "
    "AND source_url IS NULL) "
    "OR (source_kind = 'web' AND document_id IS NULL AND document_version_id IS NULL "
    "AND chunk_index IS NULL AND source_url IS NOT NULL "
    "AND source_url LIKE 'https://%' AND char_length(source_url) <= 2048)"
)


def upgrade() -> None:
    # Jobs
    op.alter_column("knowledge_extraction_jobs", "document_id", nullable=True)
    op.add_column(
        "knowledge_extraction_jobs",
        sa.Column("source_kind", sa.String(16), nullable=False, server_default="document"),
    )
    op.add_column(
        "knowledge_extraction_jobs",
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column("knowledge_extraction_jobs", sa.Column("topic", sa.String(200), nullable=True))
    op.create_foreign_key(
        "knowledge_extraction_jobs_subject_id_fkey",
        "knowledge_extraction_jobs",
        "subjects",
        ["subject_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_check_constraint(
        "ck_knowledge_jobs_source_kind",
        "knowledge_extraction_jobs",
        "source_kind IN ('document', 'web')",
    )
    op.create_check_constraint("ck_knowledge_jobs_source", "knowledge_extraction_jobs", _JOB_SOURCE)
    op.create_index("ix_knowledge_jobs_subject", "knowledge_extraction_jobs", ["subject_id"])

    # Evidence
    for column in ("document_id", "document_version_id", "chunk_index"):
        op.alter_column("knowledge_evidence", column, nullable=True)
    op.add_column(
        "knowledge_evidence",
        sa.Column("source_kind", sa.String(16), nullable=False, server_default="document"),
    )
    op.add_column("knowledge_evidence", sa.Column("source_url", sa.Text(), nullable=True))
    op.add_column("knowledge_evidence", sa.Column("source_title", sa.String(200), nullable=True))
    op.create_check_constraint(
        "ck_knowledge_evidence_source_kind",
        "knowledge_evidence",
        "source_kind IN ('document', 'web')",
    )
    op.create_check_constraint(
        "ck_knowledge_evidence_source", "knowledge_evidence", _EVIDENCE_SOURCE
    )
    op.create_index(
        "uq_knowledge_evidence_web_node",
        "knowledge_evidence",
        ["knowledge_node_id", "source_url", "quote_hash", "evidence_type"],
        unique=True,
        postgresql_where=sa.text("source_kind = 'web' AND knowledge_edge_id IS NULL"),
    )
    op.create_index(
        "uq_knowledge_evidence_web_edge",
        "knowledge_evidence",
        ["knowledge_edge_id", "source_url", "quote_hash"],
        unique=True,
        postgresql_where=sa.text("source_kind = 'web' AND knowledge_edge_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.execute("DELETE FROM knowledge_evidence WHERE source_kind = 'web'")
    op.execute("DELETE FROM knowledge_extraction_jobs WHERE source_kind = 'web'")

    op.drop_index("uq_knowledge_evidence_web_edge", table_name="knowledge_evidence")
    op.drop_index("uq_knowledge_evidence_web_node", table_name="knowledge_evidence")
    op.drop_constraint("ck_knowledge_evidence_source", "knowledge_evidence", type_="check")
    op.drop_constraint("ck_knowledge_evidence_source_kind", "knowledge_evidence", type_="check")
    op.drop_column("knowledge_evidence", "source_title")
    op.drop_column("knowledge_evidence", "source_url")
    op.drop_column("knowledge_evidence", "source_kind")
    for column in ("chunk_index", "document_version_id", "document_id"):
        op.alter_column("knowledge_evidence", column, nullable=False)

    op.drop_index("ix_knowledge_jobs_subject", table_name="knowledge_extraction_jobs")
    op.drop_constraint("ck_knowledge_jobs_source", "knowledge_extraction_jobs", type_="check")
    op.drop_constraint("ck_knowledge_jobs_source_kind", "knowledge_extraction_jobs", type_="check")
    op.drop_constraint(
        "knowledge_extraction_jobs_subject_id_fkey", "knowledge_extraction_jobs", type_="foreignkey"
    )
    op.drop_column("knowledge_extraction_jobs", "topic")
    op.drop_column("knowledge_extraction_jobs", "subject_id")
    op.drop_column("knowledge_extraction_jobs", "source_kind")
    op.alter_column("knowledge_extraction_jobs", "document_id", nullable=False)
