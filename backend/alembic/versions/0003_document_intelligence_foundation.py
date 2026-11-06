"""document intelligence foundation (Phase 3 M1)

Creates the pgvector extension and the document, version, chunk, job, storage-cleanup and
message-citation tables (D-62, D-66, D-67, D-68), adds conversation/message scope columns and
`ai_usage_records.request_kind`, and the unique constraints on Phase 1 tables that the composite
ownership foreign keys need. Grants for the restricted application role are explicit (D-33).

`CREATE EXTENSION` needs the owner role (alembic runs as DATABASE_MIGRATION_URL), never the app role.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-06

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_TABLES = (
    "storage_cleanup",
    "documents",
    "document_versions",
    "document_chunks",
    "document_processing_jobs",
    "message_citations",
)
SCOPES = "'general', 'workspace', 'subject', 'folder', 'chapter', 'document'"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Targets of the composite ownership foreign keys below (Phase 1 tables, ids already unique).
    op.create_unique_constraint("uq_workspaces_id_user", "workspaces", ["id", "user_id"])
    op.create_unique_constraint("uq_subjects_id_workspace", "subjects", ["id", "workspace_id"])
    op.create_unique_constraint("uq_chapters_id_subject", "chapters", ["id", "subject_id"])

    op.create_table(
        "storage_cleanup",
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("reason", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.CheckConstraint("attempts >= 0", name="ck_storage_cleanup_attempts"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_storage_cleanup_id"), "storage_cleanup", ["id"], unique=False)
    op.create_index(
        "ix_storage_cleanup_pending",
        "storage_cleanup",
        ["next_attempt_at"],
        unique=False,
        postgresql_where=sa.text("done_at IS NULL"),
    )
    op.create_table(
        "documents",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("subject_id", sa.UUID(), nullable=True),
        sa.Column("folder_id", sa.UUID(), nullable=True),
        sa.Column("chapter_id", sa.UUID(), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("file_type", sa.String(length=16), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("processing_status", sa.String(length=24), nullable=False),
        sa.Column("active_version", sa.Integer(), nullable=True),
        sa.Column("latest_version", sa.Integer(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
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
        sa.CheckConstraint(
            "file_type IN ('pdf', 'pptx', 'docx', 'txt', 'md', 'png', 'jpg')",
            name="ck_documents_file_type",
        ),
        sa.CheckConstraint(
            "processing_status IN ('uploaded', 'queued', 'validating', 'extracting', 'ocr_processing', 'normalising', 'chunking', 'embedding', 'indexing', 'completed', 'failed', 'cancelled')",
            name="ck_documents_status",
        ),
        sa.CheckConstraint(
            "active_version IS NULL OR (active_version >= 1 AND active_version <= latest_version)",
            name="ck_documents_active_version",
        ),
        sa.CheckConstraint(
            "chapter_id IS NULL OR subject_id IS NOT NULL",
            name="ck_documents_chapter_needs_subject",
        ),
        sa.CheckConstraint("file_size >= 0", name="ck_documents_file_size"),
        sa.CheckConstraint(
            "folder_id IS NULL OR subject_id IS NOT NULL", name="ck_documents_folder_needs_subject"
        ),
        sa.CheckConstraint("latest_version >= 1", name="ck_documents_latest_version"),
        sa.ForeignKeyConstraint(
            ["subject_id", "workspace_id"],
            ["subjects.id", "subjects.workspace_id"],
            name="fk_documents_subject_workspace",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["workspaces.id", "workspaces.user_id"],
            name="fk_documents_workspace_owner",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "user_id", name="uq_documents_id_user"),
    )
    op.create_index(op.f("ix_documents_id"), "documents", ["id"], unique=False)
    op.create_index(
        "ix_documents_user_created", "documents", ["user_id", "created_at"], unique=False
    )
    op.create_index(
        "ix_documents_user_status", "documents", ["user_id", "processing_status"], unique=False
    )
    op.create_index(
        "ix_documents_user_workspace_subject",
        "documents",
        ["user_id", "workspace_id", "subject_id"],
        unique=False,
    )
    op.create_table(
        "document_versions",
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("processing_status", sa.String(length=24), nullable=False),
        sa.Column("extraction_method", sa.String(length=32), nullable=True),
        sa.Column("ocr_used", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("ocr_mean_confidence", sa.Float(), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("slide_count", sa.Integer(), nullable=True),
        sa.Column("word_count", sa.Integer(), nullable=True),
        sa.Column(
            "warnings",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("pipeline_version", sa.String(length=32), nullable=True),
        sa.Column("index_version", sa.Integer(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
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
        sa.CheckConstraint(
            "processing_status IN ('uploaded', 'queued', 'validating', 'extracting', 'ocr_processing', 'normalising', 'chunking', 'embedding', 'indexing', 'completed', 'failed', 'cancelled')",
            name="ck_document_versions_status",
        ),
        sa.CheckConstraint(
            "(page_count IS NULL OR page_count >= 0) AND (slide_count IS NULL OR slide_count >= 0) AND (word_count IS NULL OR word_count >= 0)",
            name="ck_document_versions_counts",
        ),
        sa.CheckConstraint("file_size >= 0", name="ck_document_versions_file_size"),
        sa.CheckConstraint("version_number >= 1", name="ck_document_versions_number"),
        sa.ForeignKeyConstraint(
            ["document_id", "user_id"],
            ["documents.id", "documents.user_id"],
            name="fk_document_versions_document_owner",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "version_number", name="uq_document_versions_number"),
        sa.UniqueConstraint("id", "document_id", name="uq_document_versions_id_document"),
        sa.UniqueConstraint("storage_key", name="uq_document_versions_storage_key"),
    )
    op.create_index(op.f("ix_document_versions_id"), "document_versions", ["id"], unique=False)
    op.create_table(
        "document_chunks",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("document_version_id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("subject_id", sa.UUID(), nullable=True),
        sa.Column("folder_id", sa.UUID(), nullable=True),
        sa.Column("chapter_id", sa.UUID(), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "content_tsv",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('english', coalesce(content, ''))", persisted=True),
            nullable=True,
        ),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("slide_number", sa.Integer(), nullable=True),
        sa.Column("section_heading", sa.Text(), nullable=True),
        sa.Column("bboxes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.Column("extraction_confidence", sa.Float(), nullable=True),
        sa.Column("embedding", Vector(768), nullable=True),
        sa.Column("embedding_model", sa.String(length=128), nullable=True),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=True),
        sa.Column("index_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.CheckConstraint("chunk_index >= 0", name="ck_document_chunks_index"),
        sa.CheckConstraint(
            "embedding IS NULL OR (embedding_model IS NOT NULL AND embedding_dimensions = 768)",
            name="ck_document_chunks_embedding_meta",
        ),
        sa.CheckConstraint("index_version >= 1", name="ck_document_chunks_index_version"),
        sa.CheckConstraint(
            "page_number IS NULL OR page_number >= 1", name="ck_document_chunks_page"
        ),
        sa.CheckConstraint(
            "slide_number IS NULL OR slide_number >= 1", name="ck_document_chunks_slide"
        ),
        sa.CheckConstraint(
            "token_count >= 0 AND char_count >= 0", name="ck_document_chunks_sizes_non_negative"
        ),
        sa.ForeignKeyConstraint(
            ["document_id", "user_id"],
            ["documents.id", "documents.user_id"],
            name="fk_document_chunks_document_owner",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id", "document_id"],
            ["document_versions.id", "document_versions.document_id"],
            name="fk_document_chunks_version_document",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_version_id", "chunk_index", name="uq_document_chunks_version_index"
        ),
        sa.UniqueConstraint("id", "user_id", name="uq_document_chunks_id_user"),
    )
    op.create_index(
        "ix_document_chunks_content_tsv",
        "document_chunks",
        ["content_tsv"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(op.f("ix_document_chunks_id"), "document_chunks", ["id"], unique=False)
    op.create_index(
        "ix_document_chunks_user_document",
        "document_chunks",
        ["user_id", "document_id"],
        unique=False,
    )
    op.create_index(
        "ix_document_chunks_user_scope",
        "document_chunks",
        ["user_id", "workspace_id", "subject_id"],
        unique=False,
    )
    op.create_table(
        "document_processing_jobs",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("document_version_id", sa.UUID(), nullable=False),
        sa.Column("pipeline_version", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("stage", sa.String(length=24), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("celery_task_id", sa.String(length=64), nullable=True),
        sa.Column(
            "cancel_requested", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
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
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_document_jobs_status",
        ),
        sa.CheckConstraint("retry_count >= 0", name="ck_document_jobs_retry_count"),
        sa.ForeignKeyConstraint(
            ["document_id", "user_id"],
            ["documents.id", "documents.user_id"],
            name="fk_document_jobs_document_owner",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id", "document_id"],
            ["document_versions.id", "document_versions.document_id"],
            name="fk_document_jobs_version_document",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_document_jobs_user_status",
        "document_processing_jobs",
        ["user_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_document_jobs_version_created",
        "document_processing_jobs",
        ["document_version_id", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_document_processing_jobs_id"), "document_processing_jobs", ["id"], unique=False
    )
    op.create_index(
        "uq_document_jobs_one_running_per_version",
        "document_processing_jobs",
        ["document_version_id"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
    )
    op.create_table(
        "message_citations",
        sa.Column("message_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("chunk_id", sa.UUID(), nullable=True),
        sa.Column("document_id", sa.UUID(), nullable=True),
        sa.Column("document_name", sa.String(length=255), nullable=False),
        sa.Column("document_version", sa.Integer(), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("slide_number", sa.Integer(), nullable=True),
        sa.Column("section_heading", sa.Text(), nullable=True),
        sa.Column("snippet", sa.Text(), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("available", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.CheckConstraint(
            "page_number IS NULL OR page_number >= 1", name="ck_message_citations_page"
        ),
        sa.CheckConstraint("rank >= 1", name="ck_message_citations_rank"),
        sa.CheckConstraint(
            "slide_number IS NULL OR slide_number >= 1", name="ck_message_citations_slide"
        ),
        sa.ForeignKeyConstraint(
            ["message_id", "user_id"],
            ["messages.id", "messages.user_id"],
            name="fk_message_citations_message_owner",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", "rank", name="uq_message_citations_message_rank"),
    )
    op.create_index(
        "ix_message_citations_document", "message_citations", ["document_id"], unique=False
    )
    op.create_index(op.f("ix_message_citations_id"), "message_citations", ["id"], unique=False)
    op.create_index("ix_message_citations_user", "message_citations", ["user_id"], unique=False)

    # Composite owner/placement FKs that only clear the link column on delete (PostgreSQL 15+), so
    # a document survives losing its folder or chapter and a citation survives losing its target,
    # while subject_id / user_id stay intact (D-53 pattern).
    op.execute(
        "ALTER TABLE documents ADD CONSTRAINT fk_documents_folder_subject "
        "FOREIGN KEY (folder_id, subject_id) REFERENCES folders (id, subject_id) "
        "ON DELETE SET NULL (folder_id)"
    )
    op.execute(
        "ALTER TABLE documents ADD CONSTRAINT fk_documents_chapter_subject "
        "FOREIGN KEY (chapter_id, subject_id) REFERENCES chapters (id, subject_id) "
        "ON DELETE SET NULL (chapter_id)"
    )
    op.execute(
        "ALTER TABLE message_citations ADD CONSTRAINT fk_message_citations_chunk_owner "
        "FOREIGN KEY (chunk_id, user_id) REFERENCES document_chunks (id, user_id) "
        "ON DELETE SET NULL (chunk_id)"
    )
    op.execute(
        "ALTER TABLE message_citations ADD CONSTRAINT fk_message_citations_document_owner "
        "FOREIGN KEY (document_id, user_id) REFERENCES documents (id, user_id) "
        "ON DELETE SET NULL (document_id)"
    )

    # Existing tables: scope of a conversation, scope/mode actually used per message, usage kind.
    op.add_column(
        "conversations",
        sa.Column(
            "scope_type",
            sa.String(length=16),
            server_default=sa.text("'general'"),
            nullable=False,
        ),
    )
    op.add_column("conversations", sa.Column("scope_id", sa.UUID(), nullable=True))
    op.create_check_constraint(
        "ck_conversations_scope_type", "conversations", f"scope_type IN ({SCOPES})"
    )
    op.create_check_constraint(
        "ck_conversations_scope_id",
        "conversations",
        "(scope_type = 'general' AND scope_id IS NULL) OR "
        "(scope_type <> 'general' AND scope_id IS NOT NULL)",
    )
    op.add_column("messages", sa.Column("scope_type", sa.String(length=16), nullable=True))
    op.add_column("messages", sa.Column("scope_id", sa.UUID(), nullable=True))
    op.add_column("messages", sa.Column("answer_mode", sa.String(length=24), nullable=True))
    op.create_check_constraint(
        "ck_messages_scope_type", "messages", f"scope_type IS NULL OR scope_type IN ({SCOPES})"
    )
    op.create_check_constraint(
        "ck_messages_answer_mode",
        "messages",
        "answer_mode IS NULL OR answer_mode IN ('document_only', 'document_first', 'general')",
    )
    op.add_column(
        "ai_usage_records",
        sa.Column(
            "request_kind", sa.String(length=16), server_default=sa.text("'chat'"), nullable=False
        ),
    )
    op.create_check_constraint(
        "ck_ai_usage_request_kind",
        "ai_usage_records",
        "request_kind IN ('chat', 'embedding', 'generation')",
    )

    # Restricted application role (D-33): DML only, never DDL. Default privileges normally cover new
    # tables; the explicit grant keeps this migration correct on databases without them.
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'axonweave_app') THEN "  # noqa: S608
        + " ".join(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON {t} TO axonweave_app;" for t in NEW_TABLES
        )
        + " END IF; END $$"
    )


def downgrade() -> None:
    op.drop_constraint("ck_ai_usage_request_kind", "ai_usage_records", type_="check")
    op.drop_column("ai_usage_records", "request_kind")
    op.drop_constraint("ck_messages_answer_mode", "messages", type_="check")
    op.drop_constraint("ck_messages_scope_type", "messages", type_="check")
    op.drop_column("messages", "answer_mode")
    op.drop_column("messages", "scope_id")
    op.drop_column("messages", "scope_type")
    op.drop_constraint("ck_conversations_scope_id", "conversations", type_="check")
    op.drop_constraint("ck_conversations_scope_type", "conversations", type_="check")
    op.drop_column("conversations", "scope_id")
    op.drop_column("conversations", "scope_type")

    # Children first. Dropping a table drops its indexes and constraints.
    for table in (
        "message_citations",
        "document_processing_jobs",
        "document_chunks",
        "document_versions",
        "documents",
        "storage_cleanup",
    ):
        op.drop_table(table)

    op.drop_constraint("uq_chapters_id_subject", "chapters", type_="unique")
    op.drop_constraint("uq_subjects_id_workspace", "subjects", type_="unique")
    op.drop_constraint("uq_workspaces_id_user", "workspaces", type_="unique")
    # The vector extension is left installed on purpose: dropping it would fail or destroy data if
    # anything else uses it, and it is harmless when unused.
