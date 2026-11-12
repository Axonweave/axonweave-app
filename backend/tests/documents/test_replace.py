# ruff: noqa: F811
"""Replace-file flow and version switch (spec 6.3; D-68)."""

import uuid

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentVersion
from app.models.document_chunk import DocumentChunk
from app.models.document_processing_job import DocumentProcessingJob
from app.repositories.document_repository import DocumentRepository
from app.storage.memory_backend import InMemoryStorageBackend
from tests.documents.helpers import make_docx, make_pdf
from tests.documents.test_documents_api import (  # noqa: F401 - fixtures
    Actor,
    alice,
    bob,
    call,
    storage,
    upload_one,
)


async def _replace(client: AsyncClient, who: Actor, doc_id: str, name: str, body: bytes):
    return await call(
        client,
        who,
        "POST",
        f"/documents/{doc_id}/replace",
        files=[("files", (name, body, "application/octet-stream"))],
    )


async def _complete_v1(db: AsyncSession, doc_id: str) -> DocumentVersion:
    """Fake completion of version 1: a chunk plus the active pointer, like the pipeline writes."""
    doc = (await db.execute(select(Document).where(Document.id == uuid.UUID(doc_id)))).scalar_one()
    ver = (
        await db.execute(
            select(DocumentVersion).where(
                DocumentVersion.document_id == doc.id, DocumentVersion.version_number == 1
            )
        )
    ).scalar_one()
    db.add(
        DocumentChunk(
            user_id=doc.user_id,
            document_id=doc.id,
            document_version_id=ver.id,
            workspace_id=doc.workspace_id,
            chunk_index=0,
            content="old text",
            token_count=2,
            char_count=8,
        )
    )
    ver.processing_status = "completed"
    await DocumentRepository(db).activate_version(doc, ver)
    doc.processing_status = "completed"
    await db.commit()
    return ver


class TestReplaceFile:
    async def test_replace_adds_version_and_keeps_old_active(
        self, client: AsyncClient, alice: Actor, storage: InMemoryStorageBackend, db_session
    ):
        doc = await upload_one(client, alice)
        await _complete_v1(db_session, doc["id"])
        resp = await _replace(client, alice, doc["id"], "new.pdf", make_pdf(b"%v2"))
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["latest_version"] == 2 and data["active_version"] == 1
        assert data["processing_status"] == "queued"
        assert "storage_key" not in data
        assert f"users/{alice.user.id}/documents/{doc['id']}/v2/original.pdf" in storage.keys()
        assert len(storage.keys()) == 2
        jobs = (await db_session.execute(select(DocumentProcessingJob))).scalars().all()
        assert sorted(j.status for j in jobs) == ["queued", "queued"]
        # Old chunks are still there and still belong to the active version.
        chunks = (await db_session.execute(select(DocumentChunk))).scalars().all()
        assert len(chunks) == 1

    async def test_version_switch_drops_old_chunks_in_one_step(
        self, client: AsyncClient, alice: Actor, storage, db_session: AsyncSession
    ):
        doc = await upload_one(client, alice)
        await _complete_v1(db_session, doc["id"])
        assert (
            await _replace(client, alice, doc["id"], "n.pdf", make_pdf(b"%v2"))
        ).status_code == 200
        document = (
            await db_session.execute(select(Document).where(Document.id == uuid.UUID(doc["id"])))
        ).scalar_one()
        await db_session.refresh(document)
        v2 = (
            await db_session.execute(
                select(DocumentVersion).where(
                    DocumentVersion.document_id == document.id, DocumentVersion.version_number == 2
                )
            )
        ).scalar_one()
        db_session.add(
            DocumentChunk(
                user_id=document.user_id,
                document_id=document.id,
                document_version_id=v2.id,
                workspace_id=document.workspace_id,
                chunk_index=0,
                content="new text",
                token_count=2,
                char_count=8,
            )
        )
        v2.processing_status = "completed"
        await DocumentRepository(db_session).activate_version(document, v2)
        await db_session.commit()
        chunks = (await db_session.execute(select(DocumentChunk))).scalars().all()
        assert [c.content for c in chunks] == ["new text"]
        assert document.active_version == 2

    async def test_download_serves_active_version_until_switch(
        self, client: AsyncClient, alice: Actor, storage, db_session
    ):
        old = make_pdf(b"%old")
        doc = await upload_one(client, alice, body=old)
        await _complete_v1(db_session, doc["id"])
        await _replace(client, alice, doc["id"], "n.pdf", make_pdf(b"%new"))
        resp = await call(client, alice, "GET", f"/documents/{doc['id']}/download")
        assert resp.status_code == 200 and resp.content == old

    async def test_replace_while_processing_is_409(
        self, client: AsyncClient, alice: Actor, storage
    ):
        doc = await upload_one(client, alice)  # v1 still queued
        resp = await _replace(client, alice, doc["id"], "n.pdf", make_pdf())
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "PROCESSING_IN_PROGRESS"

    async def test_replace_with_other_file_type_is_rejected(
        self, client: AsyncClient, alice: Actor, storage, db_session
    ):
        doc = await upload_one(client, alice)
        await _complete_v1(db_session, doc["id"])
        resp = await _replace(client, alice, doc["id"], "n.docx", make_docx())
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "FILE_TYPE_MISMATCH"
        assert len(storage.keys()) == 1

    async def test_spoofed_replacement_is_rejected(
        self, client: AsyncClient, alice: Actor, storage, db_session
    ):
        doc = await upload_one(client, alice)
        await _complete_v1(db_session, doc["id"])
        resp = await _replace(client, alice, doc["id"], "n.pdf", b"<html>not a pdf</html>")
        assert resp.status_code in (415, 422)
        assert len(storage.keys()) == 1

    async def test_other_users_document_is_404_and_stores_nothing(
        self, client: AsyncClient, alice: Actor, bob: Actor, storage, db_session
    ):
        doc = await upload_one(client, alice)
        await _complete_v1(db_session, doc["id"])
        resp = await _replace(client, bob, doc["id"], "n.pdf", make_pdf())
        assert resp.status_code == 404
        unknown = await _replace(client, bob, str(uuid.uuid4()), "n.pdf", make_pdf())
        assert unknown.status_code == 404 and unknown.json() == resp.json()
        assert len(storage.keys()) == 1

    async def test_replace_requires_authentication(self, client: AsyncClient):
        resp = await client.post(
            f"/api/v1/documents/{uuid.uuid4()}/replace",
            files=[("files", ("n.pdf", make_pdf(), "application/pdf"))],
        )
        assert resp.status_code in (401, 403)
