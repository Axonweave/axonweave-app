"""Migration 0003 on a scratch database: up, down, up again, schema equals the models, grants.

Runs the real `alembic` command against a throwaway database so the migration is exercised exactly
as in CI and in compose. The comparison is by constraint and index NAMES (and table/column sets)
against the schema that `create_all` builds from the models, because the test database itself is
built that way (D-61).
"""

import os
import subprocess
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from psycopg import sql
from sqlalchemy.engine import make_url

from tests.conftest import _test_url

BACKEND = Path(__file__).resolve().parents[2]
NEW_TABLES = [
    "documents",
    "document_versions",
    "document_chunks",
    "document_processing_jobs",
    "storage_cleanup",
    "message_citations",
]
TOUCHED = [
    *NEW_TABLES,
    "workspaces",
    "subjects",
    "chapters",
    "conversations",
    "messages",
    "ai_usage_records",
]


def _dsn(db_name: str) -> str:
    url = make_url(_test_url).set(drivername="postgresql", database=db_name)
    return url.render_as_string(hide_password=False)


def _alembic(db_name: str, *args: str) -> subprocess.CompletedProcess[str]:
    url = make_url(_test_url).set(database=db_name).render_as_string(hide_password=False)
    env = {**os.environ, "DATABASE_MIGRATION_URL": url}
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )


@pytest.fixture
def scratch_db() -> Iterator[str]:
    name = f"axonweave_mig_{uuid.uuid4().hex[:8]}"
    admin = psycopg.connect(_dsn(make_url(_test_url).database or "postgres"), autocommit=True)
    admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        yield name
    finally:
        admin.execute(
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
        )
        admin.close()


# Phase 1/2 tables predate this migration and carry their own constraint naming (0001), so for them
# only the objects migration 0003 adds are compared.
ADDED_ON_EXISTING = {
    "uq_workspaces_id_user",
    "uq_subjects_id_workspace",
    "uq_chapters_id_subject",
    "ck_conversations_scope_type",
    "ck_conversations_scope_id",
    "ck_messages_scope_type",
    "ck_messages_answer_mode",
    "ck_ai_usage_request_kind",
}


def _catalog(db_name: str) -> dict[str, set[str]]:
    """Table columns, constraint names and index names for the touched tables."""
    out: dict[str, set[str]] = {}
    with psycopg.connect(_dsn(db_name)) as conn:
        for table in TOUCHED:
            cols = {
                r[0]
                for r in conn.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = %s",
                    (table,),
                )
            }
            cons = {
                r[0]
                for r in conn.execute(
                    "SELECT conname FROM pg_constraint WHERE conrelid = %s::regclass", (table,)
                )
            }
            idx = {
                r[0]
                for r in conn.execute(
                    "SELECT indexname FROM pg_indexes WHERE schemaname = 'public' "
                    "AND tablename = %s",
                    (table,),
                )
            }
            if table not in NEW_TABLES:
                cons &= ADDED_ON_EXISTING
                idx = set()
            out[f"{table}:columns"] = cols
            out[f"{table}:constraints"] = cons
            out[f"{table}:indexes"] = idx
    return out


def _tables(db_name: str) -> set[str]:
    with psycopg.connect(_dsn(db_name)) as conn:
        return {
            r[0]
            for r in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        }


def test_upgrade_downgrade_upgrade_and_single_head(scratch_db: str) -> None:
    up = _alembic(scratch_db, "upgrade", "head")
    assert up.returncode == 0, up.stderr[-800:]
    assert set(NEW_TABLES) <= _tables(scratch_db)

    heads = _alembic(scratch_db, "heads")
    assert heads.stdout.count("(head)") == 1, heads.stdout

    down = _alembic(scratch_db, "downgrade", "0002")
    assert down.returncode == 0, down.stderr[-800:]
    left = _tables(scratch_db)
    assert not set(NEW_TABLES) & left, "downgrade left Phase 3 tables behind"
    assert {"conversations", "messages", "ai_usage_records"} <= left  # earlier phases intact

    again = _alembic(scratch_db, "upgrade", "head")
    assert again.returncode == 0, again.stderr[-800:]
    assert set(NEW_TABLES) <= _tables(scratch_db)


def test_migrated_schema_matches_the_models(scratch_db: str) -> None:
    """The names of columns, constraints and indexes the migration creates equal what the models
    declare (the test database is built from the models)."""
    assert _alembic(scratch_db, "upgrade", "head").returncode == 0
    migrated = _catalog(scratch_db)
    from_models = _catalog(make_url(_test_url).database or "")
    for key in sorted(migrated):
        # `*_pkey`, `uq_`/`ck_`/`fk_`/`ix_` names must agree; unnamed FKs get server-made names
        # that agree too because both paths use PostgreSQL's default naming.
        assert migrated[key] == from_models[key], (
            key,
            "only in migration:",
            sorted(migrated[key] - from_models[key]),
            "only in models:",
            sorted(from_models[key] - migrated[key]),
        )


def test_app_role_can_use_the_new_tables_after_migrating(scratch_db: str) -> None:
    with psycopg.connect(_dsn(scratch_db), autocommit=True) as conn:
        role = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = 'axonweave_app'").fetchone()
    if role is None:
        pytest.skip("axonweave_app role not present (no init-db.sql in this database server)")
    assert _alembic(scratch_db, "upgrade", "head").returncode == 0
    with psycopg.connect(_dsn(scratch_db)) as conn:
        # The scratch database is new, so default privileges from init-db.sql do not apply:
        # these grants come from the migration itself.
        for table in NEW_TABLES:
            granted = conn.execute(
                "SELECT has_table_privilege('axonweave_app', %s, 'SELECT,INSERT,UPDATE,DELETE')",
                (table,),
            ).fetchone()
            assert granted and granted[0], table
        ddl = conn.execute(
            "SELECT has_table_privilege('axonweave_app', 'documents', 'TRUNCATE'), "
            "has_schema_privilege('axonweave_app', 'public', 'CREATE')"
        ).fetchone()
        assert ddl == (False, False) or ddl == (False, True)  # no TRUNCATE; CREATE is not relied on


def test_vector_extension_is_created_by_the_migration(scratch_db: str) -> None:
    assert _alembic(scratch_db, "upgrade", "head").returncode == 0
    with psycopg.connect(_dsn(scratch_db)) as conn:
        row = conn.execute(
            "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
        ).fetchone()
    assert row is not None
