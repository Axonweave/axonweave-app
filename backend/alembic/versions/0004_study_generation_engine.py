"""study generation engine (Phase 4 M0)

Creates `study_materials`, `study_material_versions`, `generation_jobs` and
`study_generation_preferences` (spec 18.1 to 18.3, 16; D-78 to D-90). `ai_usage_records.request_kind`
already allows 'generation' since 0003, so it is not touched here. Grants for the restricted
application role are explicit (D-33).

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-10

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_TABLES = (
    "study_materials",
    "study_material_versions",
    "generation_jobs",
    "study_generation_preferences",
)
RESOURCE_TYPES = (
    "'summary', 'flashcards', 'quiz', 'study_guide', 'glossary', 'formula_sheet', "
    "'question_bank', 'echo'"
)
JOB_STATUSES = (
    "'pending', 'retrieving_sources', 'generating', 'validating', 'saving', "
    "'completed', 'failed', 'cancelled'"
)
ACTIVE = "'pending', 'retrieving_sources', 'generating', 'validating', 'saving'"


def _ts(name: str) -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "study_materials",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("subject_id", sa.UUID(), nullable=True),
        sa.Column("chapter_id", sa.UUID(), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("resource_type", sa.String(length=32), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default=sa.text("'completed'"), nullable=False
        ),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("generation_settings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("current_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint(f"resource_type IN ({RESOURCE_TYPES})", name="ck_study_materials_type"),
        sa.CheckConstraint("status IN ('completed', 'failed')", name="ck_study_materials_status"),
        sa.CheckConstraint("current_version >= 1", name="ck_study_materials_version"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["workspaces.id", "workspaces.user_id"],
            name="fk_study_materials_workspace_owner",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "user_id", name="uq_study_materials_id_user"),
    )
    # Subject and chapter links are cleared (not cascaded) when the subject/chapter goes (D-83).
    op.execute(
        "ALTER TABLE study_materials ADD CONSTRAINT fk_study_materials_subject_workspace "
        "FOREIGN KEY (subject_id, workspace_id) REFERENCES subjects (id, workspace_id) "
        "ON DELETE SET NULL (subject_id)"
    )
    op.execute(
        "ALTER TABLE study_materials ADD CONSTRAINT fk_study_materials_chapter_subject "
        "FOREIGN KEY (chapter_id, subject_id) REFERENCES chapters (id, subject_id) "
        "ON DELETE SET NULL (chapter_id)"
    )
    op.create_index(op.f("ix_study_materials_id"), "study_materials", ["id"])
    op.create_index("ix_study_materials_user_created", "study_materials", ["user_id", "created_at"])
    op.create_index("ix_study_materials_user_type", "study_materials", ["user_id", "resource_type"])
    op.create_index("ix_study_materials_workspace", "study_materials", ["workspace_id"])
    op.create_index("ix_study_materials_subject", "study_materials", ["subject_id"])
    op.create_index("ix_study_materials_chapter", "study_materials", ["chapter_id"])

    op.create_table(
        "study_material_versions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("study_material_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("origin", sa.String(length=16), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        _ts("created_at"),
        sa.CheckConstraint("version_number >= 1", name="ck_study_versions_number"),
        sa.CheckConstraint(
            "origin IN ('generated', 'edited', 'restored', 'regenerated')",
            name="ck_study_versions_origin",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["study_material_id", "user_id"],
            ["study_materials.id", "study_materials.user_id"],
            name="fk_study_versions_material_owner",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("study_material_id", "version_number", name="uq_study_versions_number"),
    )
    op.create_index(op.f("ix_study_material_versions_id"), "study_material_versions", ["id"])
    op.create_index("ix_study_versions_user", "study_material_versions", ["user_id"])

    op.create_table(
        "generation_jobs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("study_material_id", sa.UUID(), nullable=True),
        sa.Column("generation_type", sa.String(length=32), nullable=False),
        sa.Column(
            "status", sa.String(length=24), server_default=sa.text("'pending'"), nullable=False
        ),
        sa.Column("progress", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("model_id", sa.String(length=128), nullable=True),
        sa.Column("prompt_version", sa.String(length=80), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("request", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_stats", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("provider_calls", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "cancel_requested", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("celery_task_id", sa.String(length=64), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint(f"status IN ({JOB_STATUSES})", name="ck_generation_jobs_status"),
        sa.CheckConstraint("progress >= 0 AND progress <= 100", name="ck_generation_jobs_progress"),
        sa.CheckConstraint("provider_calls >= 0", name="ck_generation_jobs_provider_calls"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        "ALTER TABLE generation_jobs ADD CONSTRAINT fk_generation_jobs_material_owner "
        "FOREIGN KEY (study_material_id, user_id) REFERENCES study_materials (id, user_id) "
        "ON DELETE SET NULL (study_material_id)"
    )
    op.create_index(op.f("ix_generation_jobs_id"), "generation_jobs", ["id"])
    op.create_index(
        "uq_generation_jobs_active_fingerprint",
        "generation_jobs",
        ["user_id", "fingerprint"],
        unique=True,
        postgresql_where=sa.text(f"status IN ({ACTIVE})"),
    )
    op.create_index("ix_generation_jobs_user_created", "generation_jobs", ["user_id", "created_at"])
    op.create_index("ix_generation_jobs_user_status", "generation_jobs", ["user_id", "status"])
    op.create_index(
        "ix_generation_jobs_status_heartbeat", "generation_jobs", ["status", "heartbeat_at"]
    )

    op.create_table(
        "study_generation_preferences",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("language", sa.String(length=32), nullable=True),
        sa.Column("explanation_level", sa.String(length=16), nullable=True),
        sa.Column("summary_length", sa.String(length=16), nullable=True),
        sa.Column("question_difficulty", sa.String(length=16), nullable=True),
        sa.Column("include_examples", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "include_definitions", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "include_source_references",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint(
            "explanation_level IS NULL OR "
            "explanation_level IN ('beginner', 'intermediate', 'advanced')",
            name="ck_study_prefs_level",
        ),
        sa.CheckConstraint(
            "summary_length IS NULL OR summary_length IN ('short', 'medium', 'long')",
            name="ck_study_prefs_length",
        ),
        sa.CheckConstraint(
            "question_difficulty IS NULL OR "
            "question_difficulty IN ('easy', 'medium', 'hard', 'mixed')",
            name="ck_study_prefs_difficulty",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(
        op.f("ix_study_generation_preferences_id"), "study_generation_preferences", ["id"]
    )

    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'axonweave_app') THEN "  # noqa: S608
        + " ".join(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON {t} TO axonweave_app;" for t in NEW_TABLES
        )
        + " END IF; END $$"
    )


def downgrade() -> None:
    op.drop_table("study_generation_preferences")
    op.drop_table("generation_jobs")
    op.drop_table("study_material_versions")
    op.drop_table("study_materials")
