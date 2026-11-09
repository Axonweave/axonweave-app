"""Phase 3 M1 schema tests: constraints live in the database, not just in code (D-61, D-67, D-68).

Every test that expects a rejection asserts the DATABASE refused it (IntegrityError), so a service
bug could not store such a row either.
"""

import uuid
from typing import Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.vector import EMBEDDING_COLUMN_DIMENSIONS
from app.models.chapter import Chapter
from app.models.conversation import Conversation
from app.models.document import Document, DocumentVersion
from app.models.document_chunk import DocumentChunk
from app.models.document_processing_job import DocumentProcessingJob
from app.models.folder import Folder
from app.models.message import Message
from app.models.message_citation import MessageCitation
from app.models.storage_cleanup import StorageCleanup
from app.models.subject import Subject
from app.models.user import User
from app.models.workspace import Workspace
from tests.conftest import _make_user


async def _workspace(db: AsyncSession, user: User) -> Workspace:
    return (await db.execute(select(Workspace).where(Workspace.user_id == user.id))).scalar_one()


async def _tree(db: AsyncSession, user: User) -> dict[str, Any]:
    ws = await _workspace(db, user)
    subject = Subject(workspace_id=ws.id, name="Maths")
    db.add(subject)
    await db.flush()
    folder = Folder(subject_id=subject.id, name="Unit 1")
    db.add(folder)
    await db.flush()
    chapter = Chapter(subject_id=subject.id, folder_id=folder.id, title="Limits")
    db.add(chapter)
    await db.flush()
    return {"ws": ws, "subject": subject, "folder": folder, "chapter": chapter}


def _doc(user: User, ws: Workspace, **over: Any) -> Document:
    fields: dict[str, Any] = {
        "user_id": user.id,
        "workspace_id": ws.id,
        "display_name": "Notes",
        "original_filename": "notes.pdf",
        "file_type": "pdf",
        "mime_type": "application/pdf",
        "file_size": 10,
        "checksum": "a" * 64,
        "processing_status": "queued",
        "latest_version": 1,
    }
    fields.update(over)
    return Document(**fields)


async def _doc_with_version(
    db: AsyncSession, user: User, ws: Workspace, **over: Any
) -> tuple[Document, DocumentVersion]:
    doc = _doc(user, ws, **over)
    db.add(doc)
    await db.flush()
    ver = DocumentVersion(
        document_id=doc.id,
        user_id=user.id,
        version_number=1,
        storage_key=f"users/{user.id}/documents/{doc.id}/v1/original.pdf",
        file_size=10,
        checksum="a" * 64,
        processing_status="queued",
    )
    db.add(ver)
    await db.flush()
    return doc, ver


def _chunk(
    doc: Document, ver: DocumentVersion, user_id: uuid.UUID, index: int = 0, **over: Any
) -> DocumentChunk:
    fields: dict[str, Any] = {
        "user_id": user_id,
        "document_id": doc.id,
        "document_version_id": ver.id,
        "workspace_id": doc.workspace_id,
        "chunk_index": index,
        "content": "Backpropagation computes gradients.",
        "token_count": 4,
        "char_count": 35,
    }
    fields.update(over)
    return DocumentChunk(**fields)


async def _rejects(db: AsyncSession, *objs: Any) -> None:
    """Add objects and expect the database to refuse them, leaving the session usable."""
    async with db.begin_nested():
        db.add_all(objs)
        with pytest.raises(IntegrityError):
            await db.flush()
    db.expunge_all()


# ── ownership: a row can never belong to two users ───────────────────────────


async def test_chunk_of_another_users_document_is_rejected(db_session: AsyncSession) -> None:
    alice = await _make_user(db_session, email="a@example.com")
    bob = await _make_user(db_session, email="b@example.com")
    doc, ver = await _doc_with_version(db_session, alice, await _workspace(db_session, alice))
    # Bob's id on Alice's document: the (document_id, user_id) composite FK refuses it.
    await _rejects(db_session, _chunk(doc, ver, bob.id))


async def test_chunk_of_the_owner_is_accepted_and_has_a_tsvector(db_session: AsyncSession) -> None:
    alice = await _make_user(db_session, email="a@example.com")
    doc, ver = await _doc_with_version(db_session, alice, await _workspace(db_session, alice))
    db_session.add(_chunk(doc, ver, alice.id))
    await db_session.flush()
    hit = (
        await db_session.execute(
            text(
                "SELECT count(*) FROM document_chunks "
                "WHERE content_tsv @@ plainto_tsquery('english', 'gradient')"
            )
        )
    ).scalar_one()
    assert hit == 1


async def test_chunk_version_must_belong_to_the_same_document(db_session: AsyncSession) -> None:
    alice = await _make_user(db_session, email="a@example.com")
    ws = await _workspace(db_session, alice)
    doc1, _ver1 = await _doc_with_version(db_session, alice, ws)
    _doc2, ver2 = await _doc_with_version(db_session, alice, ws)
    # doc1 with doc2's version: (document_version_id, document_id) FK refuses it.
    await _rejects(db_session, _chunk(doc1, ver2, alice.id))


async def test_version_of_another_users_document_is_rejected(db_session: AsyncSession) -> None:
    alice = await _make_user(db_session, email="a@example.com")
    bob = await _make_user(db_session, email="b@example.com")
    doc, _ = await _doc_with_version(db_session, alice, await _workspace(db_session, alice))
    await _rejects(
        db_session,
        DocumentVersion(
            document_id=doc.id,
            user_id=bob.id,
            version_number=2,
            storage_key="k2",
            file_size=1,
            checksum="b" * 64,
            processing_status="queued",
        ),
    )


async def test_document_in_another_users_workspace_is_rejected(db_session: AsyncSession) -> None:
    alice = await _make_user(db_session, email="a@example.com")
    bob = await _make_user(db_session, email="b@example.com")
    await _rejects(db_session, _doc(bob, await _workspace(db_session, alice)))


async def test_citation_cannot_point_at_another_users_chunk(db_session: AsyncSession) -> None:
    alice = await _make_user(db_session, email="a@example.com")
    bob = await _make_user(db_session, email="b@example.com")
    doc, ver = await _doc_with_version(db_session, alice, await _workspace(db_session, alice))
    chunk = _chunk(doc, ver, alice.id)
    db_session.add(chunk)
    conv = Conversation(user_id=bob.id, title="x")
    db_session.add(conv)
    await db_session.flush()
    msg = Message(conversation_id=conv.id, user_id=bob.id, role="assistant", sequence_number=1)
    db_session.add(msg)
    await db_session.flush()
    await _rejects(
        db_session,
        MessageCitation(
            message_id=msg.id, user_id=bob.id, rank=1, chunk_id=chunk.id, document_name="Notes"
        ),
    )


# ── placement chain ──────────────────────────────────────────────────────────


async def test_document_placement_chain_is_consistent(db_session: AsyncSession) -> None:
    alice = await _make_user(db_session, email="a@example.com")
    t = await _tree(db_session, alice)
    ok = _doc(
        alice,
        t["ws"],
        subject_id=t["subject"].id,
        folder_id=t["folder"].id,
        chapter_id=t["chapter"].id,
    )
    db_session.add(ok)
    await db_session.flush()

    # A subject from a different workspace of the same user is rejected.
    other_ws = Workspace(user_id=alice.id, name="Other", workspace_type="personal_learning")
    db_session.add(other_ws)
    await db_session.flush()
    await _rejects(db_session, _doc(alice, other_ws, subject_id=t["subject"].id))

    # A folder or chapter without a subject is rejected (composite FKs skip NULLs; CHECKs close it).
    await _rejects(db_session, _doc(alice, t["ws"], folder_id=t["folder"].id))
    await _rejects(db_session, _doc(alice, t["ws"], chapter_id=t["chapter"].id))

    # A folder that belongs to another subject is rejected.
    other_subject = Subject(workspace_id=t["ws"].id, name="Physics")
    db_session.add(other_subject)
    await db_session.flush()
    await _rejects(
        db_session, _doc(alice, t["ws"], subject_id=other_subject.id, folder_id=t["folder"].id)
    )


async def test_deleting_a_chapter_keeps_the_document_in_its_subject(
    db_session: AsyncSession,
) -> None:
    alice = await _make_user(db_session, email="a@example.com")
    t = await _tree(db_session, alice)
    doc = _doc(alice, t["ws"], subject_id=t["subject"].id, chapter_id=t["chapter"].id)
    db_session.add(doc)
    await db_session.flush()
    await db_session.execute(text("DELETE FROM chapters WHERE id = :i"), {"i": t["chapter"].id})
    row = (
        await db_session.execute(
            text("SELECT subject_id, chapter_id FROM documents WHERE id = :i"), {"i": doc.id}
        )
    ).one()
    assert row.subject_id == t["subject"].id
    assert row.chapter_id is None


async def test_deleting_a_subject_deletes_its_documents_and_chunks(
    db_session: AsyncSession,
) -> None:
    alice = await _make_user(db_session, email="a@example.com")
    t = await _tree(db_session, alice)
    doc, ver = await _doc_with_version(db_session, alice, t["ws"], subject_id=t["subject"].id)
    db_session.add(_chunk(doc, ver, alice.id))
    await db_session.flush()
    await db_session.execute(text("DELETE FROM subjects WHERE id = :i"), {"i": t["subject"].id})
    for table in ("documents", "document_versions", "document_chunks"):
        count = (await db_session.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one()  # noqa: S608
        assert count == 0, table


# ── idempotency (D-68) ───────────────────────────────────────────────────────


async def test_duplicate_chunk_index_for_a_version_is_rejected(db_session: AsyncSession) -> None:
    alice = await _make_user(db_session, email="a@example.com")
    doc, ver = await _doc_with_version(db_session, alice, await _workspace(db_session, alice))
    db_session.add(_chunk(doc, ver, alice.id, index=0))
    await db_session.flush()
    await _rejects(db_session, _chunk(doc, ver, alice.id, index=0))
    db_session.add(_chunk(doc, ver, alice.id, index=1))  # a different index is fine
    await db_session.flush()


async def test_only_one_running_job_per_version(db_session: AsyncSession) -> None:
    alice = await _make_user(db_session, email="a@example.com")
    doc, ver = await _doc_with_version(db_session, alice, await _workspace(db_session, alice))

    def job(status: str) -> DocumentProcessingJob:
        return DocumentProcessingJob(
            user_id=alice.id,
            document_id=doc.id,
            document_version_id=ver.id,
            pipeline_version="1",
            status=status,
            stage=status,
        )

    db_session.add_all([job("running"), job("queued"), job("failed"), job("succeeded")])
    await db_session.flush()  # any number of non-running jobs is fine
    await _rejects(db_session, job("running"))  # a second running job for the version is not


async def test_a_second_version_may_run_while_the_first_runs(db_session: AsyncSession) -> None:
    alice = await _make_user(db_session, email="a@example.com")
    doc, ver1 = await _doc_with_version(db_session, alice, await _workspace(db_session, alice))
    ver2 = DocumentVersion(
        document_id=doc.id,
        user_id=alice.id,
        version_number=2,
        storage_key="k-v2",
        file_size=1,
        checksum="c" * 64,
        processing_status="queued",
    )
    db_session.add(ver2)
    await db_session.flush()
    for v in (ver1, ver2):
        db_session.add(
            DocumentProcessingJob(
                user_id=alice.id,
                document_id=doc.id,
                document_version_id=v.id,
                pipeline_version="1",
                status="running",
                stage="extracting",
            )
        )
    await db_session.flush()


async def test_duplicate_version_number_is_rejected(db_session: AsyncSession) -> None:
    alice = await _make_user(db_session, email="a@example.com")
    doc, _ = await _doc_with_version(db_session, alice, await _workspace(db_session, alice))
    await _rejects(
        db_session,
        DocumentVersion(
            document_id=doc.id,
            user_id=alice.id,
            version_number=1,
            storage_key="other",
            file_size=1,
            checksum="d" * 64,
            processing_status="queued",
        ),
    )


# ── embeddings: never mix models or dimensions (D-69) ────────────────────────


async def test_embedding_needs_matching_model_metadata(db_session: AsyncSession) -> None:
    alice = await _make_user(db_session, email="a@example.com")
    doc, ver = await _doc_with_version(db_session, alice, await _workspace(db_session, alice))
    vec = [0.1] * EMBEDDING_COLUMN_DIMENSIONS
    good = _chunk(
        doc,
        ver,
        alice.id,
        0,
        embedding=vec,
        embedding_model="m1",
        embedding_dimensions=EMBEDDING_COLUMN_DIMENSIONS,
    )
    db_session.add(good)
    await db_session.flush()
    await _rejects(db_session, _chunk(doc, ver, alice.id, 1, embedding=vec))  # no model recorded
    await _rejects(
        db_session,
        _chunk(
            doc, ver, alice.id, 2, embedding=vec, embedding_model="m1", embedding_dimensions=512
        ),
    )


async def test_a_vector_of_the_wrong_length_is_rejected_by_the_column(
    db_session: AsyncSession,
) -> None:
    alice = await _make_user(db_session, email="a@example.com")
    doc, ver = await _doc_with_version(db_session, alice, await _workspace(db_session, alice))
    bad = _chunk(
        doc,
        ver,
        alice.id,
        0,
        embedding=[0.1] * 10,
        embedding_model="m1",
        embedding_dimensions=EMBEDDING_COLUMN_DIMENSIONS,
    )
    async with db_session.begin_nested():
        db_session.add(bad)
        with pytest.raises(Exception, match="dimensions"):
            await db_session.flush()
    db_session.expunge_all()


# ── enumerations and counts ──────────────────────────────────────────────────


async def test_unknown_status_and_file_type_are_rejected(db_session: AsyncSession) -> None:
    alice = await _make_user(db_session, email="a@example.com")
    ws = await _workspace(db_session, alice)
    await _rejects(db_session, _doc(alice, ws, processing_status="ready"))
    await _rejects(db_session, _doc(alice, ws, file_type="html"))
    await _rejects(db_session, _doc(alice, ws, file_size=-1))
    await _rejects(db_session, _doc(alice, ws, active_version=2, latest_version=1))


async def test_chunk_page_and_slide_must_be_positive(db_session: AsyncSession) -> None:
    alice = await _make_user(db_session, email="a@example.com")
    doc, ver = await _doc_with_version(db_session, alice, await _workspace(db_session, alice))
    await _rejects(db_session, _chunk(doc, ver, alice.id, 0, page_number=0))
    await _rejects(db_session, _chunk(doc, ver, alice.id, 1, slide_number=0))
    await _rejects(
        db_session,
        _chunk(doc, ver, alice.id, 2, chunk_index=-1) if False else _chunk(doc, ver, alice.id, -1),
    )


# ── conversation scope (D-67) ────────────────────────────────────────────────


async def test_conversation_scope_check(db_session: AsyncSession) -> None:
    alice = await _make_user(db_session, email="a@example.com")
    ok_general = Conversation(user_id=alice.id, title="g")
    ok_subject = Conversation(
        user_id=alice.id, title="s", scope_type="subject", scope_id=uuid.uuid4()
    )
    db_session.add_all([ok_general, ok_subject])
    await db_session.flush()
    assert ok_general.scope_type == "general"
    await _rejects(
        db_session, Conversation(user_id=alice.id, scope_type="general", scope_id=uuid.uuid4())
    )
    await _rejects(db_session, Conversation(user_id=alice.id, scope_type="subject", scope_id=None))
    await _rejects(
        db_session, Conversation(user_id=alice.id, scope_type="galaxy", scope_id=uuid.uuid4())
    )


async def test_message_scope_and_answer_mode_are_constrained(db_session: AsyncSession) -> None:
    alice = await _make_user(db_session, email="a@example.com")
    conv = Conversation(user_id=alice.id, title="c")
    db_session.add(conv)
    await db_session.flush()

    def msg(seq: int, **over: Any) -> Message:
        return Message(
            conversation_id=conv.id, user_id=alice.id, role="user", sequence_number=seq, **over
        )

    db_session.add(
        msg(1, answer_mode="document_first", scope_type="document", scope_id=uuid.uuid4())
    )
    await db_session.flush()
    await _rejects(db_session, msg(2, answer_mode="creative"))
    await _rejects(db_session, msg(3, scope_type="galaxy"))


# ── citations survive deletion of their targets ──────────────────────────────


async def test_citation_survives_chunk_and_document_deletion(db_session: AsyncSession) -> None:
    alice = await _make_user(db_session, email="a@example.com")
    doc, ver = await _doc_with_version(db_session, alice, await _workspace(db_session, alice))
    chunk = _chunk(doc, ver, alice.id)
    db_session.add(chunk)
    conv = Conversation(user_id=alice.id, title="c")
    db_session.add(conv)
    await db_session.flush()
    msg = Message(conversation_id=conv.id, user_id=alice.id, role="assistant", sequence_number=1)
    db_session.add(msg)
    await db_session.flush()
    cit = MessageCitation(
        message_id=msg.id,
        user_id=alice.id,
        rank=1,
        chunk_id=chunk.id,
        document_id=doc.id,
        document_name="Notes",
        page_number=3,
        snippet="text",
    )
    db_session.add(cit)
    await db_session.flush()
    await db_session.execute(text("DELETE FROM documents WHERE id = :i"), {"i": doc.id})
    row = (
        await db_session.execute(
            text(
                "SELECT user_id, chunk_id, document_id, document_name, page_number "
                "FROM message_citations WHERE id = :i"
            ),
            {"i": cit.id},
        )
    ).one()
    # Links cleared, owner and name/page kept (the service also clears the snippet, D-66).
    assert row.user_id == alice.id
    assert row.chunk_id is None and row.document_id is None
    assert row.document_name == "Notes" and row.page_number == 3


async def test_citation_rank_is_unique_per_message(db_session: AsyncSession) -> None:
    alice = await _make_user(db_session, email="a@example.com")
    conv = Conversation(user_id=alice.id, title="c")
    db_session.add(conv)
    await db_session.flush()
    msg = Message(conversation_id=conv.id, user_id=alice.id, role="assistant", sequence_number=1)
    db_session.add(msg)
    await db_session.flush()
    db_session.add(MessageCitation(message_id=msg.id, user_id=alice.id, rank=1, document_name="A"))
    await db_session.flush()
    await _rejects(
        db_session, MessageCitation(message_id=msg.id, user_id=alice.id, rank=1, document_name="B")
    )
    await _rejects(
        db_session, MessageCitation(message_id=msg.id, user_id=alice.id, rank=0, document_name="B")
    )


# ── account deletion cascades to documents; the outbox row has no FK ─────────


async def test_deleting_the_user_cascades_to_all_document_tables(db_session: AsyncSession) -> None:
    alice = await _make_user(db_session, email="a@example.com")
    doc, ver = await _doc_with_version(db_session, alice, await _workspace(db_session, alice))
    db_session.add(_chunk(doc, ver, alice.id))
    db_session.add(
        DocumentProcessingJob(
            user_id=alice.id,
            document_id=doc.id,
            document_version_id=ver.id,
            pipeline_version="1",
            status="queued",
            stage="queued",
        )
    )
    db_session.add(StorageCleanup(storage_key=ver.storage_key, reason="account_deleted"))
    await db_session.flush()
    await db_session.execute(text("DELETE FROM users WHERE id = :i"), {"i": alice.id})
    for table in ("documents", "document_versions", "document_chunks", "document_processing_jobs"):
        count = (await db_session.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one()  # noqa: S608
        assert count == 0, table
    # The outbox row must outlive the cascade: it is what lets the object be deleted afterwards.
    assert (await db_session.execute(select(StorageCleanup))).scalars().one().done_at is None
