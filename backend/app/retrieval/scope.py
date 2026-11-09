"""ScopeResolver: the only way to obtain a ResolvedScope (D-73, rule 13).

A ResolvedScope holds the user id and the document ids this user may search. Its constructor is
guarded by a module-private token, so a caller cannot build one from raw ids. A scope id that is not
the caller's resolves to 404, exactly like a missing one.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.document_repository import DocumentRepository
from app.repositories.retrieval_repository import RetrievalRepository

ScopeKind = Literal["all", "workspace", "subject", "folder", "chapter", "document"]
_TOKEN = object()


@dataclass(frozen=True)
class ResolvedScope:
    user_id: uuid.UUID
    document_ids: tuple[uuid.UUID, ...]
    token: object = None

    def __post_init__(self) -> None:
        if self.token is not _TOKEN:
            raise TypeError("ResolvedScope can only be created by ScopeResolver")


def _not_found() -> HTTPException:
    return HTTPException(404, detail={"code": "RESOURCE_NOT_FOUND", "message": "Scope not found."})


class ScopeResolver:
    def __init__(self, db: AsyncSession) -> None:
        self._repo = RetrievalRepository(db)
        self._docs = DocumentRepository(db)

    async def resolve(
        self, user_id: uuid.UUID, kind: ScopeKind, scope_id: uuid.UUID | None = None
    ) -> ResolvedScope:
        if kind == "all":
            ids = await self._repo.eligible_document_ids(user_id, "all", None)
            return ResolvedScope(user_id, tuple(ids), _TOKEN)
        if scope_id is None:
            raise _not_found()
        if kind == "document":
            if await self._docs.get_owned(document_id=scope_id, user_id=user_id) is None:
                raise _not_found()
        elif not await self._repo.scope_exists(user_id, kind, scope_id):
            raise _not_found()
        ids = await self._repo.eligible_document_ids(user_id, kind, scope_id)
        return ResolvedScope(user_id, tuple(ids), _TOKEN)
