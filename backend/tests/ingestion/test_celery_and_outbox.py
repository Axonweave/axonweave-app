"""Celery wiring, safe errors, the storage_cleanup outbox processor and the stale-job sweep (M1)."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import AppEnv
from app.ingestion import errors
from app.ingestion.cleanup_service import MAX_ATTEMPTS, process_outbox
from app.ingestion.tasks import SafeTask, ping, process_cleanup_outbox, sweep_stale_jobs
from app.ingestion.worker import BEAT_SCHEDULE, celery_app, create_celery_app
from app.models.document import Document, DocumentVersion
from app.models.document_processing_job import DocumentProcessingJob
from app.models.storage_cleanup import StorageCleanup
from app.models.workspace import Workspace
from app.repositories.processing_job_repository import ProcessingJobRepository
from app.storage.base import StorageBackend, StorageError, StorageNotConfiguredError
from app.storage.keys import build_original_key
from app.storage.memory_backend import InMemoryStorageBackend
from tests.ai.test_provider_layer import make_settings
from tests.conftest import _make_user, _TestSessionLocal


async def _source(data: bytes) -> AsyncIterator[bytes]:
    yield data


# ── Celery app and eager mode ────────────────────────────────────────────────


def test_health_task_runs_eagerly(celery_eager: None) -> None:
    """Documented way to run tasks in tests: the `celery_eager` fixture (docs/AI_TESTING.md)."""
    result = ping.delay()
    assert result.get() == {"status": "ok"}


def test_tasks_do_not_run_eagerly_without_the_fixture() -> None:
    assert celery_app.conf.task_always_eager in (False, None)


def test_every_beat_entry_points_at_a_registered_task() -> None:
    assert set(BEAT_SCHEDULE) == {
        "storage-cleanup-outbox",
        "dispatch-queued-processing-jobs",
        "sweep-stale-processing-jobs",
        "dispatch-pending-generation-jobs",
        "sweep-stale-generation-jobs",
        "sweep-study-exports",
        "dispatch-pending-extraction-jobs",
        "sweep-stale-extraction-jobs",
    }
    import app.knowledge.tasks  # noqa: F401  (registers the knowledge tasks)
    import app.study.tasks  # noqa: F401  (registers the study tasks)

    for entry in BEAT_SCHEDULE.values():
        assert entry["task"] in celery_app.tasks, entry["task"]
        assert entry["schedule"] > 0


def test_celery_config_is_safe_by_default() -> None:
    conf = celery_app.conf
    assert conf.task_serializer == "json" and list(conf.accept_content) == ["json"]  # no pickle
    assert conf.task_acks_late and conf.task_reject_on_worker_lost
    assert conf.worker_prefetch_multiplier == 1
    assert conf.task_soft_time_limit < conf.task_time_limit
    assert str(conf.timezone) == "UTC"


def test_without_a_broker_url_the_app_still_imports(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CELERY_BROKER_URL", raising=False)  # Celery reads this variable itself
    app = create_celery_app(make_settings(celery_broker_url=""))
    assert app.conf.broker_url == "memory://"


def test_tasks_use_the_safe_base_class_with_bounded_retries() -> None:
    for task in (ping, process_cleanup_outbox, sweep_stale_jobs):
        assert isinstance(task, SafeTask)
        assert task.autoretry_for == (errors.TransientTaskError,)
        assert task.retry_backoff and task.retry_jitter
        assert 0 <= task.max_retries <= 10


# ── safe error codes ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("exc", "code"),
    [
        (SoftTimeLimitExceeded(), errors.TASK_TIMEOUT),
        (StorageNotConfiguredError(), "STORAGE_NOT_CONFIGURED"),
        (errors.TransientTaskError(), errors.STORAGE_UNAVAILABLE),
        (RuntimeError("postgresql://user:secret@host/db /var/data/secret.pdf"), errors.INTERNAL),
        (ValueError("document text: the patient's name is ..."), errors.INTERNAL),
    ],
)
def test_safe_error_code_never_carries_exception_text(exc: BaseException, code: str) -> None:
    result = errors.safe_error_code(exc)
    assert result == code
    assert not str(exc) or str(exc) not in result


# ── outbox processor ─────────────────────────────────────────────────────────


class FlakyStorage(InMemoryStorageBackend):
    def __init__(self) -> None:
        super().__init__(AppEnv.testing)
        self.fail = True

    async def delete(self, key: str) -> None:
        if self.fail:
            raise StorageError("down")
        await super().delete(key)


def _key() -> str:
    return build_original_key(uuid.uuid4(), uuid.uuid4(), 1, "pdf")


async def _seed(storage: StorageBackend, key: str, reason: str = "document_deleted") -> None:
    await storage.put(key, _source(b"data"), content_type="application/pdf")
    async with _TestSessionLocal() as db:
        db.add(StorageCleanup(storage_key=key, reason=reason))
        await db.commit()


async def test_outbox_deletes_the_object_and_marks_the_row_done() -> None:
    storage = InMemoryStorageBackend(AppEnv.testing)
    key = _key()
    await _seed(storage, key)
    result = await process_outbox(_TestSessionLocal, storage)
    assert (result.deleted, result.failed) == (1, 0)
    assert not await storage.exists(key)
    async with _TestSessionLocal() as db:
        row = (await db.execute(select(StorageCleanup))).scalars().one()
        assert row.done_at is not None and row.last_error_code is None
    # Running again does nothing: done rows are not claimed.
    again = await process_outbox(_TestSessionLocal, storage)
    assert (again.deleted, again.failed) == (0, 0)


async def test_outbox_retries_with_backoff_then_succeeds() -> None:
    storage = FlakyStorage()
    key = _key()
    await _seed(storage, key)
    now = datetime.now(UTC)

    first = await process_outbox(_TestSessionLocal, storage, now=now)
    assert (first.deleted, first.failed) == (0, 1)
    assert await storage.exists(key)  # still there: nothing is forgotten until delete succeeded
    async with _TestSessionLocal() as db:
        row = (await db.execute(select(StorageCleanup))).scalars().one()
        assert row.attempts == 1 and row.done_at is None
        assert row.last_error_code == "STORAGE_ERROR"
        assert row.next_attempt_at > now  # backed off

    # Not due yet: untouched.
    assert (await process_outbox(_TestSessionLocal, storage, now=now)).failed == 0

    storage.fail = False
    later = now + timedelta(hours=7)
    done = await process_outbox(_TestSessionLocal, storage, now=later)
    assert done.deleted == 1
    assert not await storage.exists(key)


async def test_outbox_stops_retrying_after_max_attempts_and_reports_it() -> None:
    storage = FlakyStorage()
    await _seed(storage, _key())
    clock = datetime.now(UTC)
    for _ in range(MAX_ATTEMPTS):
        clock += timedelta(hours=7)
        await process_outbox(_TestSessionLocal, storage, now=clock)
    clock += timedelta(hours=7)
    final = await process_outbox(_TestSessionLocal, storage, now=clock)
    assert final.failed == 0 and final.exhausted == 1  # not claimed any more, but counted


async def test_outbox_never_acts_on_a_key_it_could_not_have_generated() -> None:
    storage = InMemoryStorageBackend(AppEnv.testing)
    victim = _key()
    await storage.put(victim, _source(b"keep"), content_type="application/pdf")
    async with _TestSessionLocal() as db:
        db.add(StorageCleanup(storage_key="../../etc/passwd", reason="tampered"))
        db.add(StorageCleanup(storage_key="users/x/documents/y/v1/original.pdf", reason="tampered"))
        await db.commit()
    result = await process_outbox(_TestSessionLocal, storage)
    assert result.skipped_invalid == 2 and result.deleted == 0
    assert await storage.exists(victim)
    async with _TestSessionLocal() as db:
        rows = (await db.execute(select(StorageCleanup))).scalars().all()
        assert all(
            r.done_at is not None and r.last_error_code == errors.INVALID_STORAGE_KEY for r in rows
        )


async def test_outbox_survives_the_deletion_of_the_owner(db_session: AsyncSession) -> None:
    """The point of the outbox (D-66): the account is gone but the object is still removed."""
    storage = InMemoryStorageBackend(AppEnv.testing)
    alice = await _make_user(db_session, email="a@example.com")
    ws = (await db_session.execute(select(Workspace))).scalars().one()
    doc = Document(
        user_id=alice.id,
        workspace_id=ws.id,
        display_name="n",
        original_filename="n.pdf",
        file_type="pdf",
        mime_type="application/pdf",
        file_size=4,
        checksum="a" * 64,
        processing_status="completed",
        latest_version=1,
    )
    db_session.add(doc)
    await db_session.flush()
    key = build_original_key(alice.id, doc.id, 1, "pdf")
    db_session.add(
        DocumentVersion(
            document_id=doc.id,
            user_id=alice.id,
            version_number=1,
            storage_key=key,
            file_size=4,
            checksum="a" * 64,
            processing_status="completed",
        )
    )
    await storage.put(key, _source(b"data"), content_type="application/pdf")
    # What the delete service will do: write the outbox rows, then delete the user (cascade).
    db_session.add(StorageCleanup(storage_key=key, reason="account_deleted"))
    await db_session.flush()
    await db_session.execute(text("DELETE FROM users WHERE id = :i"), {"i": alice.id})
    await db_session.commit()

    result = await process_outbox(_TestSessionLocal, storage)
    assert result.deleted == 1
    assert not await storage.exists(key)


# ── stale job sweep ──────────────────────────────────────────────────────────


async def _running_job(
    db: AsyncSession, *, age: timedelta
) -> tuple[Document, DocumentProcessingJob]:
    user = await _make_user(db, email=f"{uuid.uuid4().hex[:6]}@example.com")
    ws = (await db.execute(select(Workspace).where(Workspace.user_id == user.id))).scalar_one()
    doc = Document(
        user_id=user.id,
        workspace_id=ws.id,
        display_name="n",
        original_filename="n.pdf",
        file_type="pdf",
        mime_type="application/pdf",
        file_size=4,
        checksum="a" * 64,
        processing_status="extracting",
        latest_version=1,
    )
    db.add(doc)
    await db.flush()
    ver = DocumentVersion(
        document_id=doc.id,
        user_id=user.id,
        version_number=1,
        storage_key=f"k-{uuid.uuid4().hex}",
        file_size=4,
        checksum="a" * 64,
        processing_status="extracting",
    )
    db.add(ver)
    await db.flush()
    seen = datetime.now(UTC) - age
    job = DocumentProcessingJob(
        user_id=user.id,
        document_id=doc.id,
        document_version_id=ver.id,
        pipeline_version="1",
        status="running",
        stage="extracting",
        started_at=seen,
        heartbeat_at=seen,
    )
    db.add(job)
    await db.flush()
    return doc, job


async def test_sweep_fails_only_jobs_with_no_recent_sign_of_life(db_session: AsyncSession) -> None:
    stale_doc, stale_job = await _running_job(db_session, age=timedelta(hours=3))
    fresh_doc, fresh_job = await _running_job(db_session, age=timedelta(seconds=5))
    now = datetime.now(UTC)
    repo = ProcessingJobRepository(db_session)
    failed = await repo.fail_stale_running(now - timedelta(minutes=30), now, errors.WORKER_LOST)
    assert failed == 1

    await db_session.refresh(stale_job)
    await db_session.refresh(fresh_job)
    await db_session.refresh(stale_doc)
    await db_session.refresh(fresh_doc)
    assert stale_job.status == "failed" and stale_job.error_code == errors.WORKER_LOST
    assert stale_job.completed_at is not None
    assert stale_doc.processing_status == "failed"  # mirrored from the version (D-68)
    assert fresh_job.status == "running" and fresh_doc.processing_status == "extracting"
    version_status = (
        await db_session.execute(
            select(DocumentVersion.processing_status).where(
                DocumentVersion.id == stale_job.document_version_id
            )
        )
    ).scalar_one()
    assert version_status == "failed"
