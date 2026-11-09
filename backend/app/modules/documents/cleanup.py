"""One place that turns "these documents are about to be deleted" into outbox rows (D-66).

Every delete path that cascades to documents (document, subject, workspace, account) calls one of
these inside the same transaction, BEFORE deleting the parent. Folder and chapter deletion do not
need it: their foreign keys only clear the link, the documents stay (see models/document.py).
"""

import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.document_repository import DocumentRepository
from app.repositories.storage_cleanup_repository import StorageCleanupRepository


async def _enqueue(db: AsyncSession, keys: Sequence[str], reason: str) -> int:
    if keys:
        await StorageCleanupRepository(db).enqueue(keys, reason)
    return len(keys)


async def enqueue_for_document(
    db: AsyncSession, *, document_id: uuid.UUID, user_id: uuid.UUID
) -> int:
    keys = await DocumentRepository(db).storage_keys_for_document(
        document_id=document_id, user_id=user_id
    )
    return await _enqueue(db, keys, "document_deleted")


async def enqueue_for_subject(db: AsyncSession, subject_id: uuid.UUID) -> int:
    return await _enqueue(
        db, await DocumentRepository(db).storage_keys_for_subject(subject_id), "subject_deleted"
    )


async def enqueue_for_workspace(db: AsyncSession, workspace_id: uuid.UUID) -> int:
    return await _enqueue(
        db,
        await DocumentRepository(db).storage_keys_for_workspace(workspace_id),
        "workspace_deleted",
    )


async def enqueue_for_user(db: AsyncSession, user_id: uuid.UUID) -> int:
    return await _enqueue(
        db, await DocumentRepository(db).storage_keys_for_user(user_id), "account_deleted"
    )
