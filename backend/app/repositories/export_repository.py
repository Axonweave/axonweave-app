"""Owner-scoped reads for the user data export (D-24); each joins up to workspaces.user_id."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_log import ActivityLog
from app.models.ai_usage_record import AiUsageRecord
from app.models.chapter import Chapter
from app.models.conversation import Conversation
from app.models.document import Document
from app.models.flashcard import Flashcard, FlashcardSet
from app.models.folder import Folder
from app.models.message import Message, MessageFeedback
from app.models.quiz import QuizAttempt
from app.models.study_material import StudyMaterial, StudyMaterialVersion
from app.models.study_preferences import StudyGenerationPreferences
from app.models.subject import Subject
from app.models.workspace import Workspace


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


class ExportRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def workspaces(self, user_id: uuid.UUID) -> list[dict[str, Any]]:
        rows = (
            (
                await self._db.execute(
                    select(Workspace).where(Workspace.user_id == user_id).order_by(Workspace.name)
                )
            )
            .scalars()
            .all()
        )
        return [
            {
                "id": str(w.id),
                "name": w.name,
                "description": w.description,
                "workspace_type": w.workspace_type,
                "is_default": w.is_default,
                "archived_at": _iso(w.archived_at),
                "created_at": _iso(w.created_at),
                "updated_at": _iso(w.updated_at),
            }
            for w in rows
        ]

    async def subjects(self, user_id: uuid.UUID) -> list[dict[str, Any]]:
        rows = (
            (
                await self._db.execute(
                    select(Subject)
                    .join(Workspace, Subject.workspace_id == Workspace.id)
                    .where(Workspace.user_id == user_id)
                    .order_by(Subject.name)
                )
            )
            .scalars()
            .all()
        )
        return [
            {
                "id": str(s.id),
                "workspace_id": str(s.workspace_id),
                "name": s.name,
                "description": s.description,
                "archived_at": _iso(s.archived_at),
                "created_at": _iso(s.created_at),
                "updated_at": _iso(s.updated_at),
            }
            for s in rows
        ]

    async def folders(self, user_id: uuid.UUID) -> list[dict[str, Any]]:
        rows = (
            (
                await self._db.execute(
                    select(Folder)
                    .join(Subject, Folder.subject_id == Subject.id)
                    .join(Workspace, Subject.workspace_id == Workspace.id)
                    .where(Workspace.user_id == user_id)
                    .order_by(Folder.name)
                )
            )
            .scalars()
            .all()
        )
        return [
            {
                "id": str(f.id),
                "subject_id": str(f.subject_id),
                "parent_folder_id": str(f.parent_folder_id) if f.parent_folder_id else None,
                "name": f.name,
                "description": f.description,
                "archived_at": _iso(f.archived_at),
                "created_at": _iso(f.created_at),
                "updated_at": _iso(f.updated_at),
            }
            for f in rows
        ]

    async def chapters(self, user_id: uuid.UUID) -> list[dict[str, Any]]:
        rows = (
            (
                await self._db.execute(
                    select(Chapter)
                    .join(Subject, Chapter.subject_id == Subject.id)
                    .join(Workspace, Subject.workspace_id == Workspace.id)
                    .where(Workspace.user_id == user_id)
                    .order_by(Chapter.title)
                )
            )
            .scalars()
            .all()
        )
        return [
            {
                "id": str(c.id),
                "subject_id": str(c.subject_id),
                "folder_id": str(c.folder_id) if c.folder_id else None,
                "title": c.title,
                "description": c.description,
                "status": c.status,
                "display_order": c.display_order,
                "archived_at": _iso(c.archived_at),
                "created_at": _iso(c.created_at),
                "updated_at": _iso(c.updated_at),
            }
            for c in rows
        ]

    async def activity(self, user_id: uuid.UUID) -> list[dict[str, Any]]:
        rows = (
            (
                await self._db.execute(
                    select(ActivityLog)
                    .where(ActivityLog.user_id == user_id)
                    .order_by(ActivityLog.created_at.desc())
                )
            )
            .scalars()
            .all()
        )
        return [
            {
                "action": a.action,
                "entity_type": a.entity_type,
                "entity_name": a.entity_name,
                "created_at": _iso(a.created_at),
            }
            for a in rows
        ]

    # ── AI data (D-53): the user's own conversations, answers, feedback and usage ──────────────

    async def ai_conversations(self, user_id: uuid.UUID) -> list[dict[str, Any]]:
        """Conversations with their messages and feedback. Content is the user's own data."""
        conversations = (
            (
                await self._db.execute(
                    select(Conversation)
                    .where(Conversation.user_id == user_id)
                    .order_by(Conversation.created_at.asc())
                )
            )
            .scalars()
            .all()
        )
        messages = (
            (
                await self._db.execute(
                    select(Message)
                    .where(Message.user_id == user_id)
                    .order_by(Message.conversation_id, Message.sequence_number)
                )
            )
            .scalars()
            .all()
        )
        feedback = (
            (
                await self._db.execute(
                    select(MessageFeedback).where(MessageFeedback.user_id == user_id)
                )
            )
            .scalars()
            .all()
        )
        feedback_by_message = {f.message_id: f for f in feedback}
        by_conversation: dict[uuid.UUID, list[dict[str, Any]]] = {}
        for m in messages:
            fb = feedback_by_message.get(m.id)
            by_conversation.setdefault(m.conversation_id, []).append(
                {
                    "id": str(m.id),
                    "role": m.role,
                    "status": m.status,
                    "sequence_number": m.sequence_number,
                    "content": m.content,
                    "model_id": m.model_id,
                    "prompt_key": m.prompt_key,
                    "prompt_version": m.prompt_version,
                    "input_tokens": m.input_tokens,
                    "output_tokens": m.output_tokens,
                    "usage_source": m.usage_source,
                    "finish_reason": m.finish_reason,
                    "error_code": m.error_code,
                    "superseded_at": _iso(m.superseded_at),
                    "created_at": _iso(m.created_at),
                    "feedback": {
                        "rating": fb.rating,
                        "feedback_text": fb.feedback_text,
                        "created_at": _iso(fb.created_at),
                    }
                    if fb
                    else None,
                }
            )
        return [
            {
                "id": str(c.id),
                "title": c.title,
                "status": c.status,
                "model_id": c.model_id,
                "last_message_at": _iso(c.last_message_at),
                "created_at": _iso(c.created_at),
                "messages": by_conversation.get(c.id, []),
            }
            for c in conversations
        ]

    async def ai_usage(self, user_id: uuid.UUID) -> list[dict[str, Any]]:
        rows = (
            (
                await self._db.execute(
                    select(AiUsageRecord)
                    .where(AiUsageRecord.user_id == user_id)
                    .order_by(AiUsageRecord.created_at.asc())
                )
            )
            .scalars()
            .all()
        )
        return [
            {
                "created_at": _iso(r.created_at),
                "conversation_id": str(r.conversation_id) if r.conversation_id else None,
                "message_id": str(r.message_id) if r.message_id else None,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "reasoning_tokens": r.reasoning_tokens,
                "usage_source": r.usage_source,
                "estimated_cost": str(r.estimated_cost) if r.estimated_cost is not None else None,
                "currency": r.currency,
                "pricing_version": r.pricing_version,
                "request_status": r.request_status,
                "error_code": r.error_code,
                "duration_ms": r.duration_ms,
            }
            for r in rows
        ]

    async def documents(self, user_id: uuid.UUID) -> list[dict[str, Any]]:
        """Metadata only (D-66): no file bytes, no extracted text, no storage key, no checksum."""
        rows = (
            (
                await self._db.execute(
                    select(Document)
                    .where(Document.user_id == user_id)
                    .order_by(Document.created_at.asc())
                )
            )
            .scalars()
            .all()
        )
        return [
            {
                "id": str(d.id),
                "workspace_id": str(d.workspace_id),
                "subject_id": str(d.subject_id) if d.subject_id else None,
                "folder_id": str(d.folder_id) if d.folder_id else None,
                "chapter_id": str(d.chapter_id) if d.chapter_id else None,
                "display_name": d.display_name,
                "original_filename": d.original_filename,
                "file_type": d.file_type,
                "file_size": d.file_size,
                "processing_status": d.processing_status,
                "created_at": _iso(d.created_at),
                "archived_at": _iso(d.archived_at),
            }
            for d in rows
        ]

    # Study materials (Phase 4, D-100): the user's own generated content. Quiz answer keys are not
    # part of this export (they are generated reference data, and never leave before submission).

    async def study_materials(self, user_id: uuid.UUID) -> list[dict[str, Any]]:
        materials = (
            (
                await self._db.execute(
                    select(StudyMaterial)
                    .where(StudyMaterial.user_id == user_id)
                    .order_by(StudyMaterial.created_at)
                )
            )
            .scalars()
            .all()
        )
        versions = (
            (
                await self._db.execute(
                    select(StudyMaterialVersion)
                    .where(StudyMaterialVersion.user_id == user_id)
                    .order_by(
                        StudyMaterialVersion.study_material_id,
                        StudyMaterialVersion.version_number,
                    )
                )
            )
            .scalars()
            .all()
        )
        by_material: dict[uuid.UUID, list[dict[str, Any]]] = {}
        for v in versions:
            by_material.setdefault(v.study_material_id, []).append(
                {
                    "version_number": v.version_number,
                    "origin": v.origin,
                    "created_at": _iso(v.created_at),
                    "content": v.content,
                }
            )
        cards = (
            await self._db.execute(
                select(Flashcard, FlashcardSet.study_material_id)
                .join(FlashcardSet, Flashcard.flashcard_set_id == FlashcardSet.id)
                .where(Flashcard.user_id == user_id)
                .order_by(FlashcardSet.study_material_id, Flashcard.display_order)
            )
        ).all()
        cards_by_material: dict[uuid.UUID, list[dict[str, Any]]] = {}
        for card, material_id in cards:
            cards_by_material.setdefault(material_id, []).append(
                {
                    "front": card.front,
                    "back": card.back,
                    "explanation": card.explanation,
                    "card_type": card.card_type,
                    "difficulty": card.difficulty,
                    "is_favourite": card.is_favourite,
                }
            )
        return [
            {
                "id": str(m.id),
                "workspace_id": str(m.workspace_id),
                "subject_id": str(m.subject_id) if m.subject_id else None,
                "chapter_id": str(m.chapter_id) if m.chapter_id else None,
                "title": m.title,
                "resource_type": m.resource_type,
                "status": m.status,
                "current_version": m.current_version,
                "content": m.content,
                "generation_settings": m.generation_settings,
                "created_at": _iso(m.created_at),
                "updated_at": _iso(m.updated_at),
                "archived_at": _iso(m.archived_at),
                "versions": by_material.get(m.id, []),
                "flashcards": cards_by_material.get(m.id, []),
            }
            for m in materials
        ]

    async def quiz_attempts(self, user_id: uuid.UUID) -> list[dict[str, Any]]:
        rows = (
            (
                await self._db.execute(
                    select(QuizAttempt)
                    .where(QuizAttempt.user_id == user_id)
                    .order_by(QuizAttempt.started_at)
                )
            )
            .scalars()
            .all()
        )
        return [
            {
                "quiz_id": str(a.quiz_id),
                "status": a.status,
                "started_at": _iso(a.started_at),
                "submitted_at": _iso(a.submitted_at),
                "score": str(a.score) if a.score is not None else None,
                "graded_questions": a.graded_questions,
                "percentage": str(a.percentage) if a.percentage is not None else None,
            }
            for a in rows
        ]

    async def study_preferences(self, user_id: uuid.UUID) -> dict[str, Any] | None:
        row = (
            await self._db.execute(
                select(StudyGenerationPreferences).where(
                    StudyGenerationPreferences.user_id == user_id
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        return {
            "language": row.language,
            "explanation_level": row.explanation_level,
            "summary_length": row.summary_length,
            "question_difficulty": row.question_difficulty,
            "include_examples": row.include_examples,
            "include_definitions": row.include_definitions,
            "include_source_references": row.include_source_references,
        }
