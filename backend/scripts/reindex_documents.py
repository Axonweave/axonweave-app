"""Find documents whose embeddings are stale or missing and re-queue them (Phase 3, D-69).

Stale means: a different index_version or embedding model than the configured one, or no vector.
Dry run by default (prints counts only, never text); pass --apply to re-queue through the normal
reprocess path, which needs the worker and Redis running.

  docker compose exec backend python scripts/reindex_documents.py
  docker compose exec backend python scripts/reindex_documents.py --apply
"""

import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.database.connection import AsyncSessionLocal  # noqa: E402
from app.models.document import Document  # noqa: E402
from app.modules.documents.scanner import get_scanner  # noqa: E402
from app.modules.documents.service import DocumentService  # noqa: E402
from app.repositories.retrieval_repository import RetrievalRepository  # noqa: E402
from app.storage.factory import get_storage_backend  # noqa: E402


async def main(apply: bool) -> int:
    s = get_settings()
    if not s.embedding_provider or not s.embedding_model:
        print("Refusing: EMBEDDING_PROVIDER and EMBEDDING_MODEL must be configured.")
        return 2
    async with AsyncSessionLocal() as db:
        ids = await RetrievalRepository(db).documents_needing_reindex(
            s.embedding_index_version, s.embedding_model
        )
        owners: dict[uuid.UUID, uuid.UUID] = {}
        if ids:
            rows = await db.execute(
                select(Document.id, Document.user_id).where(Document.id.in_(ids))
            )
            owners = {r[0]: r[1] for r in rows.all()}
    print(f"documents needing reindex: {len(ids)}")
    if not apply or not ids:
        if ids:
            print("dry run: pass --apply to re-queue them")
        return 0
    done = failed = 0
    for doc_id in ids:
        owner = owners.get(doc_id)
        if owner is None:
            continue
        async with AsyncSessionLocal() as db:
            service = DocumentService(db, get_storage_backend(), get_scanner(s), s)
            try:
                await service.reprocess(user_id=owner, document_id=doc_id)
                done += 1
            except HTTPException:  # e.g. already processing: skipped, picked up on the next run
                failed += 1
    print(f"re-queued: {done}, skipped: {failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main("--apply" in sys.argv)))
