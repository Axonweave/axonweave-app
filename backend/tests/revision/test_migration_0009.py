"""Migration 0009 on a scratch database: Phase 4 data survives, schema equals the models, downgrade
and upgrade again work, and the new constraints enforce ownership.

Uses the real `alembic` command (as CI and compose do). The comparison with the models is by
column, constraint and index NAMES because the test database itself is built from the models (D-61).
"""

import json
import uuid
from collections.abc import Iterator

import psycopg
import pytest
from psycopg import sql
from sqlalchemy.engine import make_url

from tests.conftest import _test_url
from tests.documents.test_migration import _alembic, _dsn

NEW_TABLES = [
    "flashcard_scheduling",
    "flashcard_reviews",
    "revision_sessions",
    "revision_recommendations",
]
TOUCHED = [*NEW_TABLES, "quiz_attempts", "quiz_attempt_answers", "quiz_questions", "flashcards"]
# Names added by 0009 on tables that existed before (older tables carry their own naming from
# earlier migrations, so only these are compared for them).
ADDED_ON_EXISTING = {
    "uq_flashcards_id_user",
    "ck_quiz_attempts_status",
    "ck_quiz_attempts_evaluation_status",
    "ck_quiz_attempts_time_taken",
    "ck_quiz_attempt_answers_grading_method",
    "ck_quiz_attempt_answers_evaluation_status",
}
ADDED_INDEXES = {
    "ix_quiz_questions_user_topic",
    "uq_quiz_attempts_submit_key",
    "ix_quiz_attempts_user_submitted",
    "ix_quiz_attempt_answers_user_question",
}


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


def _catalog(db_name: str) -> dict[str, set[str]]:
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
                idx &= ADDED_INDEXES
            out[f"{table}:columns"] = cols
            out[f"{table}:constraints"] = cons
            out[f"{table}:indexes"] = idx
    return out


def _seed_phase4(db_name: str) -> dict[str, uuid.UUID]:
    """Insert one user with a flashcard, a quiz and two submitted attempts, at schema 0008."""
    ids = {
        k: uuid.uuid4()
        for k in ("user", "ws", "mat", "quiz", "q1", "q2", "q3", "att", "att_open", "set", "card")
    }
    mat_card = uuid.uuid4()
    with psycopg.connect(_dsn(db_name), autocommit=True) as c:
        c.execute(
            "INSERT INTO users (id, email, password_hash) VALUES (%s, 'm@example.com', 'x')",
            (ids["user"],),
        )
        c.execute(
            "INSERT INTO workspaces (id, user_id, name) VALUES (%s, %s, 'w')",
            (ids["ws"], ids["user"]),
        )
        for mid, rtype in ((ids["mat"], "quiz"), (mat_card, "flashcards")):
            c.execute(
                "INSERT INTO study_materials (id, user_id, workspace_id, title, resource_type, "
                "content, generation_settings, source_metadata) "
                "VALUES (%s, %s, %s, 't', %s, '{}', '{}', '{}')",
                (mid, ids["user"], ids["ws"], rtype),
            )
        c.execute(
            "INSERT INTO quizzes (id, user_id, study_material_id, title) VALUES (%s, %s, %s, 'q')",
            (ids["quiz"], ids["user"], ids["mat"]),
        )
        for i, (qid, qtype) in enumerate(
            (
                (ids["q1"], "multiple_choice"),
                (ids["q2"], "multiple_choice"),
                (ids["q3"], "short_answer"),
            )
        ):
            c.execute(
                "INSERT INTO quiz_questions (id, user_id, quiz_id, question, question_type, "
                "difficulty, correct_answers, display_order) "
                "VALUES (%s, %s, %s, 'Q?', %s, 'easy', %s, %s)",
                (qid, ids["user"], ids["quiz"], qtype, json.dumps(["a"]), i),
            )
        c.execute(
            "INSERT INTO quiz_attempts (id, user_id, quiz_id, status, question_order, started_at, "
            "submitted_at, score, total_questions, graded_questions, percentage) "
            "VALUES (%s, %s, %s, 'submitted', '[]', '2026-01-01 10:00+00', '2026-01-01 10:07+00', "
            "1, 3, 2, 50)",
            (ids["att"], ids["user"], ids["quiz"]),
        )
        for qid, correct in ((ids["q1"], True), (ids["q2"], False), (ids["q3"], None)):
            c.execute(
                "INSERT INTO quiz_attempt_answers (id, user_id, attempt_id, question_id, "
                "is_correct, submitted_at) VALUES (%s, %s, %s, %s, %s, '2026-01-01 10:07+00')",
                (uuid.uuid4(), ids["user"], ids["att"], qid, correct),
            )
        c.execute(
            "INSERT INTO quiz_attempts (id, user_id, quiz_id, status, question_order, started_at) "
            "VALUES (%s, %s, %s, 'in_progress', '[]', '2026-01-02 10:00+00')",
            (ids["att_open"], ids["user"], ids["quiz"]),
        )
        c.execute(
            "INSERT INTO flashcard_sets (id, user_id, study_material_id) VALUES (%s, %s, %s)",
            (ids["set"], ids["user"], mat_card),
        )
        c.execute(
            "INSERT INTO flashcards (id, user_id, flashcard_set_id, front, back, card_type, "
            "difficulty, display_order) VALUES (%s, %s, %s, 'f', 'b', 'basic', 'easy', 0)",
            (ids["card"], ids["user"], ids["set"]),
        )
    return ids


def test_upgrade_preserves_phase4_data_and_backfills(scratch_db: str) -> None:
    assert _alembic(scratch_db, "upgrade", "0008").returncode == 0
    ids = _seed_phase4(scratch_db)

    up = _alembic(scratch_db, "upgrade", "head")
    assert up.returncode == 0, up.stderr[-800:]
    heads = _alembic(scratch_db, "heads")
    assert heads.stdout.count("(head)") == 1, heads.stdout

    with psycopg.connect(_dsn(scratch_db)) as c:
        row = c.execute(
            "SELECT status, score, total_questions, correct_answers, incorrect_answers, "
            "unanswered, max_score, time_taken_seconds, evaluation_status, "
            "submit_idempotency_key FROM quiz_attempts WHERE id = %s",
            (ids["att"],),
        ).fetchone()
        assert row is not None
        assert row[:3] == ("submitted", 1, 3)
        assert row[3:5] == (1, 1)  # backfilled from the stored answers
        assert row[5] is None  # unanswered cannot be proven from old rows, so it stays NULL
        assert row[6] == 2 and row[7] == 420
        assert row[8:] == ("not_required", None)

        open_row = c.execute(
            "SELECT status, correct_answers, time_taken_seconds FROM quiz_attempts WHERE id = %s",
            (ids["att_open"],),
        ).fetchone()
        assert open_row == ("in_progress", None, None)

        answers = c.execute(
            "SELECT is_correct, grading_method, evaluation_status, max_score, ai_assisted "
            "FROM quiz_attempt_answers WHERE attempt_id = %s ORDER BY is_correct NULLS LAST",
            (ids["att"],),
        ).fetchall()
        assert [a[:3] for a in answers] == [
            (False, "auto", "graded"),
            (True, "auto", "graded"),
            (None, "self_assessment", "not_graded"),
        ]
        assert answers[2][3] == 0 and answers[0][3] == 1
        assert not any(a[4] for a in answers)

        assert c.execute("SELECT count(*) FROM quiz_questions").fetchone() == (3,)
        assert c.execute("SELECT topic FROM quiz_questions LIMIT 1").fetchone() == (None,)
        assert c.execute("SELECT count(*) FROM flashcards").fetchone() == (1,)


def test_downgrade_and_upgrade_again_keep_phase4_data(scratch_db: str) -> None:
    assert _alembic(scratch_db, "upgrade", "0008").returncode == 0
    ids = _seed_phase4(scratch_db)
    assert _alembic(scratch_db, "upgrade", "head").returncode == 0

    down = _alembic(scratch_db, "downgrade", "0008")
    assert down.returncode == 0, down.stderr[-800:]
    with psycopg.connect(_dsn(scratch_db)) as c:
        tables = {
            r[0] for r in c.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'")
        }
        assert not set(NEW_TABLES) & tables
        cols = {
            r[0]
            for r in c.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'quiz_attempts'"
            )
        }
        assert "correct_answers" not in cols
        assert c.execute("SELECT count(*) FROM quiz_attempts").fetchone() == (2,)
        assert c.execute(
            "SELECT count(*) FROM quiz_attempt_answers WHERE attempt_id = %s", (ids["att"],)
        ).fetchone() == (3,)
        assert c.execute("SELECT count(*) FROM flashcards").fetchone() == (1,)

    again = _alembic(scratch_db, "upgrade", "head")
    assert again.returncode == 0, again.stderr[-800:]


def test_migrated_schema_matches_the_models(scratch_db: str) -> None:
    assert _alembic(scratch_db, "upgrade", "head").returncode == 0
    migrated = _catalog(scratch_db)
    from_models = _catalog(make_url(_test_url).database or "")
    for key in sorted(migrated):
        assert migrated[key] == from_models[key], (
            key,
            "only in migration:",
            sorted(migrated[key] - from_models[key]),
            "only in models:",
            sorted(from_models[key] - migrated[key]),
        )


def test_ownership_and_uniqueness_constraints(scratch_db: str) -> None:
    assert _alembic(scratch_db, "upgrade", "0008").returncode == 0
    ids = _seed_phase4(scratch_db)
    assert _alembic(scratch_db, "upgrade", "head").returncode == 0
    other = uuid.uuid4()
    with psycopg.connect(_dsn(scratch_db), autocommit=True) as c:
        c.execute(
            "INSERT INTO users (id, email, password_hash) VALUES (%s, 'o@example.com', 'x')",
            (other,),
        )
        ins = (
            "INSERT INTO flashcard_scheduling "
            "(id, user_id, flashcard_id, due_at, scheduler_version) "
            "VALUES (gen_random_uuid(), %s, %s, now(), 'v1')"
        )
        # another user cannot hold scheduling for this user's card (composite ownership FK)
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            c.execute(ins, (other, ids["card"]))
        c.execute(ins, (ids["user"], ids["card"]))
        with pytest.raises(psycopg.errors.UniqueViolation):  # one scheduling row per user and card
            c.execute(ins, (ids["user"], ids["card"]))
        with pytest.raises(psycopg.errors.CheckViolation):
            c.execute(
                "UPDATE flashcard_scheduling SET state = 'bogus' WHERE user_id = %s",
                (ids["user"],),
            )

        rev = (
            "INSERT INTO flashcard_reviews (id, user_id, flashcard_id, idempotency_key, rating, "
            "reviewed_at, elapsed_days, scheduled_days, previous_state, resulting_state, "
            "scheduler_version) "
            "VALUES (gen_random_uuid(), %s, %s, %s, %s, now(), 0, 1, '{}', '{}', 'v1')"
        )
        c.execute(rev, (ids["user"], ids["card"], "k1", "good"))
        with pytest.raises(psycopg.errors.UniqueViolation):  # retried request, same key
            c.execute(rev, (ids["user"], ids["card"], "k1", "good"))
        with pytest.raises(psycopg.errors.CheckViolation):
            c.execute(rev, (ids["user"], ids["card"], "k2", "meh"))
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            c.execute(rev, (other, ids["card"], "k3", "good"))

        # deleting the card removes its scheduling and review history (D-110)
        c.execute("DELETE FROM flashcards WHERE id = %s", (ids["card"],))
        assert c.execute("SELECT count(*) FROM flashcard_scheduling").fetchone() == (0,)
        assert c.execute("SELECT count(*) FROM flashcard_reviews").fetchone() == (0,)

        sess = (
            "INSERT INTO revision_sessions (id, user_id, status, started_at, last_activity_at) "
            "VALUES (gen_random_uuid(), %s, 'active', now(), now())"
        )
        c.execute(sess, (ids["user"],))
        with pytest.raises(psycopg.errors.UniqueViolation):  # one active session per user
            c.execute(sess, (ids["user"],))
        c.execute(sess, (other,))

        rec = (
            "INSERT INTO revision_recommendations (id, user_id, recommendation_type, dedupe_key, "
            "reason, priority, status) "
            "VALUES (gen_random_uuid(), %s, 'topic', 'topic:x', 'why', 'high', %s)"
        )
        c.execute(rec, (ids["user"], "pending"))
        with pytest.raises(psycopg.errors.UniqueViolation):  # deduplicated while pending
            c.execute(rec, (ids["user"], "pending"))
        c.execute(rec, (ids["user"], "dismissed"))
        c.execute(rec, (ids["user"], "dismissed"))

        # deleting the account removes all Phase 5 rows (D-110)
        c.execute("DELETE FROM users WHERE id = %s", (ids["user"],))
        for t in ("revision_sessions", "revision_recommendations"):
            n = c.execute(f"SELECT count(*) FROM {t} WHERE user_id = %s", (ids["user"],))  # noqa: S608
            assert n.fetchone() == (0,)
