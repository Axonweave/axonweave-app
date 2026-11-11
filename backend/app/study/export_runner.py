"""Produces one export file (worker side, D-100). Logs carry ids, format, size and error codes only,
never content. The render runs in a thread so a large document cannot block the event loop."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.models.study_export import StudyExport
from app.models.study_material import StudyMaterial
from app.repositories.flashcard_repository import FlashcardRepository
from app.repositories.quiz_repository import QuizRepository
from app.repositories.study_export_repository import StudyExportRepository
from app.storage.base import StorageBackend, StorageError
from app.storage.keys import build_export_key
from app.study.errors import EXPORT_RENDER_FAILED
from app.study.exporting import ExportInput, render

logger = structlog.get_logger(__name__)
STORAGE_FAILED = "EXPORT_STORAGE_FAILED"


async def load_export_input(db: AsyncSession, material: StudyMaterial) -> ExportInput:
    """The material's current content. Quiz questions come WITHOUT the answer key columns."""
    payload = material.content.get("payload")
    payload = payload if isinstance(payload, dict) else {}
    cards: list[dict[str, object]] = []
    questions: list[dict[str, object]] = []
    if material.resource_type == "flashcards":
        repo = FlashcardRepository(db)
        card_set = await repo.get_set_for_material(material.id, material.user_id)
        if card_set is not None:
            cards = [
                {
                    "front": c.front,
                    "back": c.back,
                    "explanation": c.explanation,
                    "card_type": c.card_type,
                    "difficulty": c.difficulty,
                }
                for c in await repo.cards(card_set.id, material.user_id)
            ]
    elif material.resource_type == "quiz":
        quiz_repo = QuizRepository(db)
        quiz = await quiz_repo.get_quiz_for_material(material.id, material.user_id)
        if quiz is not None:
            questions = [
                {
                    "question": q.question,
                    "question_type": q.question_type,
                    "difficulty": q.difficulty,
                    "options": q.options,
                }
                for q in await quiz_repo.questions(quiz.id, material.user_id)
            ]
    return ExportInput(material.resource_type, material.title, payload, cards, questions)


async def _one(data: bytes) -> AsyncIterator[bytes]:
    yield data


async def run_export(
    factory: async_sessionmaker[AsyncSession],
    storage: StorageBackend,
    settings: Settings,
    export_id: uuid.UUID,
) -> str:
    """Returns the final status. Idempotent: only a `pending` export is processed."""
    async with factory() as db:
        claimed = await db.execute(
            update(StudyExport)
            .where(StudyExport.id == export_id, StudyExport.status == "pending")
            .values(updated_at=datetime.now(UTC))
            .returning(StudyExport.id)
        )
        if claimed.scalar_one_or_none() is None:
            return "skipped"
        row = await StudyExportRepository(db).get(export_id)
        material = await db.get(StudyMaterial, row.study_material_id) if row is not None else None
        if row is None or material is None or material.user_id != row.user_id:
            return "skipped"
        user_id, fmt = row.user_id, row.export_format
        data = await load_export_input(db, material)
        await db.commit()

    try:
        content = await asyncio.to_thread(render, fmt, data)
    except Exception as exc:
        logger.warning(
            "export_render_failed", export_id=str(export_id), error_type=type(exc).__name__
        )
        return await _fail(factory, export_id, EXPORT_RENDER_FAILED)

    key = build_export_key(user_id, export_id, fmt)
    try:
        await storage.put(key, _one(content), content_type="application/octet-stream")
    except StorageError as exc:
        logger.warning("export_store_failed", export_id=str(export_id), code=exc.code)
        return await _fail(factory, export_id, STORAGE_FAILED)

    async with factory() as db:
        await db.execute(
            update(StudyExport)
            .where(StudyExport.id == export_id)
            .values(
                status="completed",
                storage_key=key,
                size_bytes=len(content),
                expires_at=datetime.now(UTC) + timedelta(seconds=settings.study_export_ttl_seconds),
                updated_at=datetime.now(UTC),
            )
        )
        await db.commit()
    logger.info("export_completed", export_id=str(export_id), format=fmt, size=len(content))
    return "completed"


async def _fail(factory: async_sessionmaker[AsyncSession], export_id: uuid.UUID, code: str) -> str:
    async with factory() as db:
        await StudyExportRepository(db).mark_failed(export_id, code)
        await db.commit()
    return "failed"


async def expire_exports(
    factory: async_sessionmaker[AsyncSession], storage: StorageBackend, now: datetime | None = None
) -> int:
    """Delete the files of exports past their expiry and mark the rows `expired`."""
    clock = now or datetime.now(UTC)
    count = 0
    async with factory() as db:
        for row in await StudyExportRepository(db).due_for_expiry(clock, 100):
            if row.storage_key:
                try:
                    await storage.delete(row.storage_key)
                except StorageError as exc:
                    logger.warning("export_expiry_delete_failed", code=exc.code)
                    continue
            row.status = "expired"
            row.storage_key = None
            count += 1
        await db.commit()
    return count
