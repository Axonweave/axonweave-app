"""Phase 3 M2: upload and document management API (spec 4, 19.1; D-64, D-66, D-71, D-72)."""

import asyncio
import struct
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import AppEnv, Settings, get_settings
from app.main import app
from app.models.chapter import Chapter
from app.models.document import Document, DocumentVersion
from app.models.document_processing_job import DocumentProcessingJob
from app.models.folder import Folder
from app.models.storage_cleanup import StorageCleanup
from app.models.subject import Subject
from app.models.workspace import Workspace
from app.modules.documents.routes import get_document_storage
from app.storage.base import StorageNotConfiguredError
from app.storage.memory_backend import InMemoryStorageBackend
from tests.conftest import _make_session, _make_user
from tests.documents.helpers import make_docx, make_jpeg, make_pdf, make_png, make_pptx

PASSWORD = "TestPassword123!"


class Actor:
    def __init__(self, user: Any, token: str, csrf: str, ws_id: uuid.UUID, subject_id: uuid.UUID):
        self.user = user
        self.cookies = {"aw_session": token, "csrf_token": csrf}
        self.headers = {"X-CSRF-Token": csrf}
        self.ws_id = ws_id
        self.subject_id = subject_id


async def _actor(db: AsyncSession, email: str) -> Actor:
    user = await _make_user(db, email=email)
    token, csrf = await _make_session(db, user)
    ws = Workspace(user_id=user.id, name="WS", workspace_type="personal_learning", is_default=False)
    db.add(ws)
    await db.flush()
    subject = Subject(workspace_id=ws.id, name="Subject")
    db.add(subject)
    await db.flush()
    await db.commit()
    return Actor(user, token, csrf, ws.id, subject.id)


@pytest.fixture
async def alice(db_session: AsyncSession) -> Actor:
    return await _actor(db_session, "alice-docs@example.com")


@pytest.fixture
async def bob(db_session: AsyncSession) -> Actor:
    return await _actor(db_session, "bob-docs@example.com")


@pytest.fixture
def storage() -> Iterator[InMemoryStorageBackend]:
    backend = InMemoryStorageBackend(AppEnv.testing)
    app.dependency_overrides[get_document_storage] = lambda: backend
    yield backend
    app.dependency_overrides.pop(get_document_storage, None)


def configure(**changes: Any) -> None:
    settings: Settings = get_settings().model_copy(update=changes)
    app.dependency_overrides[get_settings] = lambda: settings


async def call(client: AsyncClient, who: Actor, method: str, url: str, **kw: Any):
    return await client.request(
        method, f"/api/v1{url}", cookies=who.cookies, headers=who.headers, **kw
    )


async def upload(
    client: AsyncClient,
    who: Actor,
    files: list[tuple[str, bytes]],
    *,
    extra: dict[str, str] | None = None,
):
    data = {"workspace_id": str(who.ws_id), "subject_id": str(who.subject_id)}
    data.update(extra or {})
    return await call(
        client,
        who,
        "POST",
        "/documents/upload",
        data=data,
        files=[("files", (name, content, "application/octet-stream")) for name, content in files],
    )


async def upload_one(client: AsyncClient, who: Actor, name: str = "notes.pdf", body: bytes = b""):
    resp = await upload(client, who, [(name, body or make_pdf())])
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["documents"][0]


class TestUpload:
    async def test_upload_stores_object_row_and_queued_job(
        self, client: AsyncClient, alice: Actor, storage: InMemoryStorageBackend, db_session
    ):
        body = make_pdf()
        doc = await upload_one(client, alice, "Lecture 1.pdf", body)
        assert doc["processing_status"] == "queued"
        assert doc["file_type"] == "pdf"
        assert doc["mime_type"] == "application/pdf"
        assert doc["file_size"] == len(body)
        assert "storage_key" not in doc and "checksum" not in doc

        assert len(storage.keys()) == 1
        key = storage.keys()[0]
        assert key == f"users/{alice.user.id}/documents/{doc['id']}/v1/original.pdf"
        job = (await db_session.execute(select(DocumentProcessingJob))).scalar_one()
        assert job.status == "queued" and str(job.document_id) == doc["id"]
        version = (await db_session.execute(select(DocumentVersion))).scalar_one()
        assert version.processing_status == "queued"

    async def test_every_supported_type_is_accepted(
        self, client: AsyncClient, alice: Actor, storage: InMemoryStorageBackend
    ):
        files = [
            ("a.pdf", make_pdf()),
            ("b.docx", make_docx()),
            ("c.pptx", make_pptx()),
            ("d.txt", b"plain text"),
            ("e.md", b"# heading\n"),
        ]
        resp = await upload(client, alice, files)
        assert resp.status_code == 201, resp.text
        types = sorted(d["file_type"] for d in resp.json()["data"]["documents"])
        assert types == ["docx", "md", "pdf", "pptx", "txt"]
        resp = await upload(client, alice, [("f.png", make_png())])
        assert resp.json()["data"]["documents"][0]["file_type"] == "png"
        resp = await upload(client, alice, [("g.jpeg", make_jpeg())])
        assert resp.json()["data"]["documents"][0]["file_type"] == "jpg"

    async def test_name_is_sanitised_and_never_part_of_the_key(
        self, client: AsyncClient, alice: Actor, storage: InMemoryStorageBackend
    ):
        doc = await upload_one(client, alice, "../../etc/pass\x00wd‮.pdf")
        assert "/" not in doc["display_name"] and ".." not in doc["display_name"]
        assert "\x00" not in doc["display_name"] and "‮" not in doc["display_name"]
        key = storage.keys()[0]
        assert "passwd" not in key and "etc" not in key

    async def test_partial_success_reports_rejected_files(
        self, client: AsyncClient, alice: Actor, storage: InMemoryStorageBackend
    ):
        resp = await upload(client, alice, [("ok.pdf", make_pdf()), ("bad.pdf", b"not a pdf")])
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert len(data["documents"]) == 1
        assert data["rejected"][0]["filename"] == "bad.pdf"
        assert data["rejected"][0]["code"] == "FILE_CONTENT_MISMATCH"

    async def test_all_rejected_returns_the_error_status(
        self, client: AsyncClient, alice: Actor, storage: InMemoryStorageBackend
    ):
        resp = await upload(client, alice, [("bad.pdf", b"not a pdf")])
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "FILE_CONTENT_MISMATCH"
        assert storage.keys() == []

    async def test_placement_with_folder_and_chapter(
        self, client: AsyncClient, alice: Actor, storage: InMemoryStorageBackend, db_session
    ):
        folder = Folder(subject_id=alice.subject_id, name="F")
        db_session.add(folder)
        await db_session.flush()
        chapter = Chapter(subject_id=alice.subject_id, folder_id=folder.id, title="C")
        db_session.add(chapter)
        await db_session.commit()
        resp = await upload(
            client,
            alice,
            [("a.pdf", make_pdf())],
            extra={"folder_id": str(folder.id), "chapter_id": str(chapter.id)},
        )
        doc = resp.json()["data"]["documents"][0]
        assert doc["folder_id"] == str(folder.id) and doc["chapter_id"] == str(chapter.id)

    async def test_foreign_placement_is_404(
        self, client: AsyncClient, alice: Actor, bob: Actor, storage: InMemoryStorageBackend
    ):
        resp = await upload(
            client, alice, [("a.pdf", make_pdf())], extra={"workspace_id": str(bob.ws_id)}
        )
        assert resp.status_code == 404
        resp = await upload(
            client, alice, [("a.pdf", make_pdf())], extra={"subject_id": str(bob.subject_id)}
        )
        assert resp.status_code == 404
        assert storage.keys() == []

    async def test_folder_needs_subject(
        self, client: AsyncClient, alice: Actor, storage: InMemoryStorageBackend
    ):
        resp = await call(
            client,
            alice,
            "POST",
            "/documents/upload",
            data={"workspace_id": str(alice.ws_id), "folder_id": str(uuid.uuid4())},
            files=[("files", ("a.pdf", make_pdf(), "application/pdf"))],
        )
        assert resp.status_code == 422

    async def test_no_files_and_bad_content_type(
        self, client: AsyncClient, alice: Actor, storage: InMemoryStorageBackend
    ):
        resp = await call(
            client, alice, "POST", "/documents/upload", data={"workspace_id": str(alice.ws_id)}
        )
        assert resp.status_code in (415, 422)
        resp = await call(client, alice, "POST", "/documents/upload", json={"a": 1})
        assert resp.status_code == 415

    async def test_too_many_files(
        self, client: AsyncClient, alice: Actor, storage: InMemoryStorageBackend
    ):
        configure(doc_max_files_per_request=2)
        resp = await upload(client, alice, [(f"{i}.pdf", make_pdf()) for i in range(3)])
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "TOO_MANY_FILES"
        assert storage.keys() == []

    async def test_storage_not_configured_is_503_and_nothing_else_breaks(
        self, client: AsyncClient, alice: Actor, monkeypatch: pytest.MonkeyPatch
    ):
        def unconfigured() -> None:
            raise StorageNotConfiguredError

        monkeypatch.setattr("app.modules.documents.routes.get_storage_backend", unconfigured)
        for method, url in (("GET", "/documents"), ("POST", "/documents/upload")):
            resp = await call(client, alice, method, url)
            assert resp.status_code == 503, (method, url)
            assert resp.json()["error"]["code"] == "DOCUMENT_STORAGE_NOT_CONFIGURED"
        # Auth still runs first, and the rest of the app does not need storage.
        assert (await client.get("/api/v1/documents")).status_code == 401
        assert (await call(client, alice, "GET", "/auth/me")).status_code == 200


class TestHostileUploads:
    async def test_oversize_file_is_413_and_not_stored(
        self, client: AsyncClient, alice: Actor, storage: InMemoryStorageBackend
    ):
        configure(doc_max_file_bytes=1024)
        resp = await upload(client, alice, [("big.pdf", make_pdf(b"x" * 4096))])
        assert resp.status_code == 413
        assert resp.json()["error"]["code"] == "FILE_TOO_LARGE"
        assert storage.keys() == []

    async def test_oversize_body_is_cut_off_by_content_length(
        self, client: AsyncClient, alice: Actor, storage: InMemoryStorageBackend
    ):
        configure(doc_max_file_bytes=1024, doc_max_files_per_request=1)
        # Limit = 1 file * 1 KiB + 1 MiB overhead; send clearly more than that.
        resp = await upload(client, alice, [("huge.pdf", make_pdf(b"x" * (2 * 1024 * 1024)))])
        assert resp.status_code == 413
        assert resp.json()["error"]["code"] == "UPLOAD_TOO_LARGE"
        assert storage.keys() == []

    @pytest.mark.parametrize(
        ("name", "body"),
        [
            ("fake.pdf", b"plain text pretending to be a pdf"),
            ("fake.txt", make_pdf()),  # pdf bytes, txt name
            ("fake.png", make_pdf()),
            ("fake.docx", make_pdf()),
            ("fake.jpg", make_png()),  # png bytes, jpg name
            ("fake.docx", make_pptx()),  # pptx content, docx name
            ("fake.pptx", make_docx()),
            ("empty.txt", b""),
        ],
    )
    async def test_spoofed_type_or_empty_is_rejected(
        self, client: AsyncClient, alice: Actor, storage: InMemoryStorageBackend, name, body
    ):
        resp = await upload(client, alice, [(name, body)])
        assert resp.status_code == 422
        assert storage.keys() == []

    async def test_browser_mime_is_ignored(
        self, client: AsyncClient, alice: Actor, storage: InMemoryStorageBackend
    ):
        resp = await call(
            client,
            alice,
            "POST",
            "/documents/upload",
            data={"workspace_id": str(alice.ws_id)},
            files=[("files", ("a.pdf", b"<html><script>alert(1)</script>", "application/pdf"))],
        )
        assert resp.status_code == 422

    @pytest.mark.parametrize(
        "name", ["page.html", "page.htm", "x.svg", "x.js", "x.exe", "x.doc", "x.ppt", "noext"]
    )
    async def test_unsupported_extensions(
        self, client: AsyncClient, alice: Actor, storage: InMemoryStorageBackend, name
    ):
        resp = await upload(client, alice, [(name, b"<html></html>")])
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"

    async def test_html_hidden_in_text_file_is_rejected(
        self, client: AsyncClient, alice: Actor, storage: InMemoryStorageBackend
    ):
        for body in (b"<!DOCTYPE html><html></html>", b"  <script>alert(1)</script>"):
            resp = await upload(client, alice, [("notes.txt", body)])
            assert resp.status_code == 422
            assert resp.json()["error"]["code"] == "HTML_NOT_ALLOWED"

    async def test_binary_text_and_bad_utf8_rejected(
        self, client: AsyncClient, alice: Actor, storage: InMemoryStorageBackend
    ):
        assert (await upload(client, alice, [("a.txt", b"ab\x00cd")])).status_code == 422
        assert (await upload(client, alice, [("a.txt", b"\xff\xfe\xfa bad")])).status_code == 422

    async def test_zip_bomb_by_ratio_is_rejected(
        self, client: AsyncClient, alice: Actor, storage: InMemoryStorageBackend
    ):
        bomb = make_docx({"word/media/huge.bin": b"\x00" * (20 * 1024 * 1024)})
        resp = await upload(client, alice, [("bomb.docx", bomb)])
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "ARCHIVE_TOO_LARGE"

    async def test_zip_total_size_and_entry_count_limits(
        self, client: AsyncClient, alice: Actor, storage: InMemoryStorageBackend
    ):
        configure(doc_zip_max_uncompressed_bytes=1000)
        big = make_docx({"word/a.bin": b"abc" * 1000})
        assert (await upload(client, alice, [("a.docx", big)])).status_code == 422
        configure(doc_zip_max_entries=2)
        many = make_docx({f"word/{i}.xml": b"<a/>" for i in range(5)})
        assert (await upload(client, alice, [("a.docx", many)])).status_code == 422

    async def test_zip_path_traversal_nested_archive_and_macros_rejected(
        self, client: AsyncClient, alice: Actor, storage: InMemoryStorageBackend
    ):
        for extra in (
            {"../evil.xml": b"x"},
            {"/abs.xml": b"x"},
            {"word\\evil.xml": b"x"},
            {"word/embedded.zip": b"PK"},
            {"word/vbaProject.bin": b"macro"},
        ):
            resp = await upload(client, alice, [("a.docx", make_docx(extra))])
            assert resp.status_code == 422, extra
        assert storage.keys() == []

    async def test_corrupt_zip_is_rejected(
        self, client: AsyncClient, alice: Actor, storage: InMemoryStorageBackend
    ):
        resp = await upload(client, alice, [("a.docx", b"PK\x03\x04 truncated nonsense")])
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "FILE_CORRUPT"

    async def test_image_decompression_bomb_is_rejected(
        self, client: AsyncClient, alice: Actor, storage: InMemoryStorageBackend
    ):
        assert (await upload(client, alice, [("a.png", make_png(60000, 60000))])).status_code == 422
        assert (
            await upload(client, alice, [("a.jpg", make_jpeg(60000, 60000))])
        ).status_code == 422
        configure(doc_image_max_pixels=10)
        assert (await upload(client, alice, [("a.png", make_png(5, 5))])).status_code == 422
        assert storage.keys() == []

    async def test_scanner_enabled_but_unavailable_fails_closed(
        self, client: AsyncClient, alice: Actor, storage: InMemoryStorageBackend
    ):
        configure(scanner_backend="clamav")
        resp = await upload(client, alice, [("a.pdf", make_pdf())])
        assert resp.status_code == 503
        assert resp.json()["error"]["code"] == "SCANNER_UNAVAILABLE"
        assert storage.keys() == []


class FakeClamd:
    """A tiny clamd: reads an INSTREAM and answers with a canned reply."""

    def __init__(self, reply: bytes):
        self.reply, self.received = reply, 0

    async def handle(self, reader, writer):
        await reader.readexactly(len(b"zINSTREAM\0"))
        while True:
            (n,) = struct.unpack("!I", await reader.readexactly(4))
            if n == 0:
                break
            self.received += len(await reader.readexactly(n))
        writer.write(self.reply)
        await writer.drain()
        writer.close()


async def _clamd(reply: bytes):
    fake = FakeClamd(reply)
    server = await asyncio.start_server(fake.handle, "127.0.0.1", 0)
    return fake, server, server.sockets[0].getsockname()[1]


class TestClamdScanner:
    async def test_clean_file_is_stored_and_streamed_to_the_scanner(
        self, client: AsyncClient, alice: Actor, storage: InMemoryStorageBackend
    ):
        fake, server, port = await _clamd(b"stream: OK\0")
        async with server:
            configure(scanner_backend="clamav", clamav_host="127.0.0.1", clamav_port=port)
            resp = await upload(client, alice, [("a.pdf", make_pdf())])
        assert resp.status_code == 201
        assert fake.received == len(make_pdf())

    async def test_infected_file_is_rejected_and_not_stored(
        self, client: AsyncClient, alice: Actor, storage: InMemoryStorageBackend
    ):
        _, server, port = await _clamd(b"stream: Eicar-Test-Signature FOUND\0")
        async with server:
            configure(scanner_backend="clamav", clamav_host="127.0.0.1", clamav_port=port)
            resp = await upload(client, alice, [("a.pdf", make_pdf())])
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "MALWARE_DETECTED"
        assert storage.keys() == []

    async def test_error_reply_and_dead_scanner_fail_closed(
        self, client: AsyncClient, alice: Actor, storage: InMemoryStorageBackend
    ):
        _, server, port = await _clamd(b"INSTREAM size limit exceeded. ERROR\0")
        async with server:
            configure(scanner_backend="clamav", clamav_host="127.0.0.1", clamav_port=port)
            resp = await upload(client, alice, [("a.pdf", make_pdf())])
        assert resp.status_code == 503
        configure(scanner_backend="clamav", clamav_host="127.0.0.1", clamav_port=port)  # now closed
        resp = await upload(client, alice, [("a.pdf", make_pdf())])
        assert resp.status_code == 503 and storage.keys() == []


class TestQuotasAndRateLimit:
    async def test_document_count_quota(
        self, client: AsyncClient, alice: Actor, storage: InMemoryStorageBackend
    ):
        configure(doc_max_documents_per_user=1)
        await upload_one(client, alice, "a.pdf")
        resp = await upload(client, alice, [("b.pdf", make_pdf())])
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "DOCUMENT_QUOTA_EXCEEDED"

    async def test_total_bytes_quota(
        self, client: AsyncClient, alice: Actor, storage: InMemoryStorageBackend
    ):
        configure(doc_max_total_bytes_per_user=len(make_pdf()) + 10)
        await upload_one(client, alice, "a.pdf")
        resp = await upload(client, alice, [("b.pdf", make_pdf())])
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "STORAGE_QUOTA_EXCEEDED"

    async def test_quota_is_per_user(
        self, client: AsyncClient, alice: Actor, bob: Actor, storage: InMemoryStorageBackend
    ):
        configure(doc_max_documents_per_user=1)
        await upload_one(client, alice, "a.pdf")
        await upload_one(client, bob, "b.pdf")

    async def test_upload_rate_limit_returns_429(
        self, client: AsyncClient, alice: Actor, storage: InMemoryStorageBackend
    ):
        configure(doc_uploads_per_minute_per_user=2)
        await upload_one(client, alice, "1.pdf")
        await upload_one(client, alice, "2.pdf")
        resp = await upload(client, alice, [("3.pdf", make_pdf())])
        assert resp.status_code == 429
        assert resp.headers.get("retry-after")


class TestReadUpdateDelete:
    async def test_get_list_filters_sort_and_pagination(
        self, client: AsyncClient, alice: Actor, storage: InMemoryStorageBackend
    ):
        a = await upload_one(client, alice, "alpha.pdf")
        await upload_one(client, alice, "beta.txt", b"hello")
        got = await call(client, alice, "GET", f"/documents/{a['id']}")
        assert got.status_code == 200 and got.json()["data"]["display_name"] == "alpha.pdf"

        listing = (await call(client, alice, "GET", "/documents")).json()
        assert listing["total"] == 2 and len(listing["data"]) == 2
        only_txt = (await call(client, alice, "GET", "/documents?file_type=txt")).json()
        assert [d["display_name"] for d in only_txt["data"]] == ["beta.txt"]
        by_name = (
            await call(client, alice, "GET", "/documents?sort_by=display_name&sort_dir=asc")
        ).json()
        assert [d["display_name"] for d in by_name["data"]] == ["alpha.pdf", "beta.txt"]
        search = (await call(client, alice, "GET", "/documents?q=ALP")).json()
        assert search["total"] == 1
        page = (await call(client, alice, "GET", "/documents?limit=1&offset=1")).json()
        assert len(page["data"]) == 1 and page["total"] == 2
        by_status = (await call(client, alice, "GET", "/documents?status=queued")).json()
        assert by_status["total"] == 2

    async def test_like_wildcards_in_search_are_literal(
        self, client: AsyncClient, alice: Actor, storage: InMemoryStorageBackend
    ):
        await upload_one(client, alice, "report.pdf")
        listing = (await call(client, alice, "GET", "/documents?q=%25")).json()
        assert listing["total"] == 0

    @pytest.mark.parametrize(
        "query",
        [
            "sort_by=password_hash",
            "sort_dir=sideways",
            "limit=1000",
            "limit=0",
            "offset=-1",
            "status=hacked",
            "file_type=exe",
            "workspace_id=not-a-uuid",
        ],
    )
    async def test_list_validates_input(
        self, client: AsyncClient, alice: Actor, storage: InMemoryStorageBackend, query
    ):
        resp = await call(client, alice, "GET", f"/documents?{query}")
        assert resp.status_code == 422

    async def test_list_never_includes_other_users_documents(
        self, client: AsyncClient, alice: Actor, bob: Actor, storage: InMemoryStorageBackend
    ):
        await upload_one(client, bob, "bobs.pdf")
        for q in ("", f"?workspace_id={bob.ws_id}", f"?subject_id={bob.subject_id}"):
            listing = (await call(client, alice, "GET", f"/documents{q}")).json()
            assert listing["total"] == 0 and listing["data"] == []

    async def test_rename_and_move(
        self, client: AsyncClient, alice: Actor, storage: InMemoryStorageBackend, db_session
    ):
        doc = await upload_one(client, alice)
        folder = Folder(subject_id=alice.subject_id, name="F")
        db_session.add(folder)
        await db_session.commit()
        resp = await call(
            client,
            alice,
            "PATCH",
            f"/documents/{doc['id']}",
            json={
                "display_name": "  New <name>.pdf ",
                "placement": {
                    "workspace_id": str(alice.ws_id),
                    "subject_id": str(alice.subject_id),
                    "folder_id": str(folder.id),
                },
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["display_name"] == "New _name_.pdf"
        assert data["folder_id"] == str(folder.id)
        assert data["original_filename"] == "notes.pdf"

    async def test_move_to_foreign_or_inconsistent_placement_is_refused(
        self, client: AsyncClient, alice: Actor, bob: Actor, storage: InMemoryStorageBackend
    ):
        doc = await upload_one(client, alice)
        url = f"/documents/{doc['id']}"
        foreign_ws = {"placement": {"workspace_id": str(bob.ws_id)}}
        assert (await call(client, alice, "PATCH", url, json=foreign_ws)).status_code == 404
        foreign_subject = {
            "placement": {"workspace_id": str(alice.ws_id), "subject_id": str(bob.subject_id)}
        }
        assert (await call(client, alice, "PATCH", url, json=foreign_subject)).status_code == 404
        orphan_folder = {
            "placement": {"workspace_id": str(alice.ws_id), "folder_id": str(uuid.uuid4())}
        }
        assert (await call(client, alice, "PATCH", url, json=orphan_folder)).status_code == 422

    async def test_patch_rejects_unknown_and_protected_fields(
        self, client: AsyncClient, alice: Actor, storage: InMemoryStorageBackend
    ):
        doc = await upload_one(client, alice)
        for body in (
            {"user_id": str(uuid.uuid4())},
            {"processing_status": "completed"},
            {"storage_key": "x"},
            {"display_name": ""},
        ):
            resp = await call(client, alice, "PATCH", f"/documents/{doc['id']}", json=body)
            assert resp.status_code == 422, body

    async def test_archive_and_restore(
        self, client: AsyncClient, alice: Actor, storage: InMemoryStorageBackend
    ):
        doc = await upload_one(client, alice)
        resp = await call(client, alice, "POST", f"/documents/{doc['id']}/archive")
        assert resp.json()["data"]["archived_at"] is not None
        assert (await call(client, alice, "GET", "/documents")).json()["total"] == 0
        assert (await call(client, alice, "GET", "/documents?include_archived=true")).json()[
            "total"
        ] == 1
        resp = await call(client, alice, "POST", f"/documents/{doc['id']}/restore")
        assert resp.json()["data"]["archived_at"] is None

    async def test_status_endpoint(
        self, client: AsyncClient, alice: Actor, storage: InMemoryStorageBackend
    ):
        doc = await upload_one(client, alice)
        resp = await call(client, alice, "GET", f"/documents/{doc['id']}/status")
        data = resp.json()["data"]
        assert data["processing_status"] == "queued"
        assert data["job_status"] == "queued" and data["error_code"] is None
        assert data["version"] == 1

    async def test_delete_removes_row_and_queues_object_cleanup(
        self, client: AsyncClient, alice: Actor, storage: InMemoryStorageBackend, db_session
    ):
        doc = await upload_one(client, alice)
        key = storage.keys()[0]
        resp = await call(client, alice, "DELETE", f"/documents/{doc['id']}")
        assert resp.status_code == 204
        assert (await call(client, alice, "GET", f"/documents/{doc['id']}")).status_code == 404
        assert (await db_session.execute(select(func.count(Document.id)))).scalar_one() == 0
        assert (await db_session.execute(select(func.count(DocumentVersion.id)))).scalar_one() == 0
        rows = (await db_session.execute(select(StorageCleanup))).scalars().all()
        assert [(r.storage_key, r.reason) for r in rows] == [(key, "document_deleted")]
        # The outbox worker would now delete the object; run it the same way the task does.
        from app.ingestion.cleanup_service import process_outbox
        from tests.conftest import _TestSessionLocal

        result = await process_outbox(_TestSessionLocal, storage)
        assert result.deleted == 1 and storage.keys() == []


class TestDownload:
    async def test_download_streams_attachment_with_safe_headers(
        self, client: AsyncClient, alice: Actor, storage: InMemoryStorageBackend
    ):
        body = make_pdf(b"unique-bytes")
        doc = await upload_one(client, alice, "My Lecture é.pdf", body)
        resp = await call(client, alice, "GET", f"/documents/{doc['id']}/download")
        assert resp.status_code == 200
        assert resp.content == body
        assert resp.headers["content-disposition"].startswith("attachment;")
        assert resp.headers["x-content-type-options"] == "nosniff"
        # The security-headers middleware sets "no-store" on every API response.
        assert "no-store" in resp.headers["cache-control"]
        assert resp.headers["content-type"] == "application/octet-stream"
        assert "users/" not in str(resp.headers)

    async def test_inline_is_pdf_or_image_only_and_sandboxed(
        self, client: AsyncClient, alice: Actor, storage: InMemoryStorageBackend
    ):
        pdf = await upload_one(client, alice, "a.pdf")
        resp = await call(client, alice, "GET", f"/documents/{pdf['id']}/inline")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.headers["content-disposition"].startswith("inline;")
        assert resp.headers["content-security-policy"] == "sandbox; default-src 'none'"
        assert resp.headers["x-content-type-options"] == "nosniff"
        png = await upload_one(client, alice, "a.png", make_png())
        resp = await call(client, alice, "GET", f"/documents/{png['id']}/inline")
        assert resp.headers["content-type"] == "image/png"
        txt = await upload_one(client, alice, "a.txt", b"hello")
        resp = await call(client, alice, "GET", f"/documents/{txt['id']}/inline")
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "INLINE_NOT_SUPPORTED"

    async def test_missing_object_is_reported_before_streaming(
        self, client: AsyncClient, alice: Actor, storage: InMemoryStorageBackend
    ):
        doc = await upload_one(client, alice)
        await storage.delete(storage.keys()[0])
        resp = await call(client, alice, "GET", f"/documents/{doc['id']}/download")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "DOCUMENT_FILE_MISSING"


class TestAccessControl:
    ID_ROUTES = [
        ("GET", "/documents/{id}"),
        ("PATCH", "/documents/{id}"),
        ("DELETE", "/documents/{id}"),
        ("POST", "/documents/{id}/archive"),
        ("POST", "/documents/{id}/restore"),
        ("GET", "/documents/{id}/status"),
        ("GET", "/documents/{id}/download"),
        ("GET", "/documents/{id}/inline"),
    ]

    @pytest.mark.parametrize(("method", "path"), ID_ROUTES)
    async def test_other_users_document_is_404_on_every_route(
        self,
        client: AsyncClient,
        alice: Actor,
        bob: Actor,
        storage: InMemoryStorageBackend,
        db_session,
        method,
        path,
    ):
        doc = await upload_one(client, alice)
        kwargs: dict[str, Any] = {"json": {"display_name": "x"}} if method == "PATCH" else {}
        resp = await call(client, bob, method, path.format(id=doc["id"]), **kwargs)
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"
        # An unknown id looks identical to someone else's id (no existence leak).
        unknown = await call(client, bob, method, path.format(id=uuid.uuid4()), **kwargs)
        assert unknown.status_code == 404 and unknown.json() == resp.json()
        # Nothing of Alice's changed.
        assert (await call(client, alice, "GET", f"/documents/{doc['id']}")).status_code == 200
        assert len(storage.keys()) == 1

    async def test_every_documents_route_requires_authentication(self, client: AsyncClient):
        schema = app.openapi()
        checked = 0
        for path, methods in schema["paths"].items():
            if not path.startswith("/api/v1/documents"):
                continue
            for method in methods:
                url = path.replace("{document_id}", str(uuid.uuid4()))
                resp = await client.request(method.upper(), url)
                assert resp.status_code == 401, (method, path)
                checked += 1
        assert checked >= 10

    async def test_inactive_account_is_refused(
        self, client: AsyncClient, alice: Actor, db_session, storage: InMemoryStorageBackend
    ):
        alice.user.status = "suspended"
        db_session.add(alice.user)
        await db_session.commit()
        resp = await call(client, alice, "GET", "/documents")
        assert resp.status_code == 403

    async def test_csrf_is_required_for_state_changes(
        self, client: AsyncClient, alice: Actor, storage: InMemoryStorageBackend
    ):
        doc = await upload_one(client, alice)
        resp = await client.delete(f"/api/v1/documents/{doc['id']}", cookies=alice.cookies)
        assert resp.status_code == 403
        assert (await call(client, alice, "GET", f"/documents/{doc['id']}")).status_code == 200

    async def test_error_bodies_never_contain_keys_or_paths(
        self, client: AsyncClient, alice: Actor, storage: InMemoryStorageBackend
    ):
        doc = await upload_one(client, alice)
        key = storage.keys()[0]
        await storage.delete(key)
        resp = await call(client, alice, "GET", f"/documents/{doc['id']}/download")
        assert key not in resp.text and "users/" not in resp.text


class TestCascadesAndExport:
    async def _doc_in(self, client, who, **extra):
        resp = await upload(client, who, [("a.pdf", make_pdf())], extra=extra)
        assert resp.status_code == 201, resp.text
        return resp.json()["data"]["documents"][0]

    async def test_subject_delete_queues_cleanup(
        self, client: AsyncClient, alice: Actor, storage: InMemoryStorageBackend, db_session
    ):
        await self._doc_in(client, alice)
        key = storage.keys()[0]
        resp = await call(
            client, alice, "DELETE", f"/workspaces/{alice.ws_id}/subjects/{alice.subject_id}"
        )
        assert resp.status_code == 204
        rows = (await db_session.execute(select(StorageCleanup))).scalars().all()
        assert [(r.storage_key, r.reason) for r in rows] == [(key, "subject_deleted")]
        assert (await db_session.execute(select(func.count(Document.id)))).scalar_one() == 0

    async def test_workspace_delete_queues_cleanup(
        self, client: AsyncClient, alice: Actor, storage: InMemoryStorageBackend, db_session
    ):
        await self._doc_in(client, alice)
        key = storage.keys()[0]
        resp = await call(client, alice, "DELETE", f"/workspaces/{alice.ws_id}")
        assert resp.status_code in (200, 204), resp.text
        rows = (await db_session.execute(select(StorageCleanup))).scalars().all()
        assert [(r.storage_key, r.reason) for r in rows] == [(key, "workspace_deleted")]

    async def test_folder_and_chapter_delete_keep_the_document(
        self, client: AsyncClient, alice: Actor, storage: InMemoryStorageBackend, db_session
    ):
        folder = Folder(subject_id=alice.subject_id, name="F")
        db_session.add(folder)
        await db_session.flush()
        chapter = Chapter(subject_id=alice.subject_id, folder_id=folder.id, title="C")
        db_session.add(chapter)
        await db_session.commit()
        doc = await self._doc_in(
            client, alice, folder_id=str(folder.id), chapter_id=str(chapter.id)
        )
        url = f"/workspaces/{alice.ws_id}/subjects/{alice.subject_id}"
        resp = await call(client, alice, "DELETE", f"{url}/chapters/{chapter.id}")
        assert resp.status_code == 204, resp.text
        got = (await call(client, alice, "GET", f"/documents/{doc['id']}")).json()["data"]
        assert got["chapter_id"] is None and got["folder_id"] == str(folder.id)
        resp = await call(client, alice, "DELETE", f"{url}/folders/{folder.id}")
        assert resp.status_code == 204, resp.text
        got = (await call(client, alice, "GET", f"/documents/{doc['id']}")).json()["data"]
        assert got["folder_id"] is None and got["chapter_id"] is None
        assert got["subject_id"] == str(alice.subject_id)
        assert len(storage.keys()) == 1
        rows = (await db_session.execute(select(func.count(StorageCleanup.id)))).scalar_one()
        assert rows == 0

    async def test_account_deletion_queues_cleanup_for_every_document(
        self, client: AsyncClient, alice: Actor, storage: InMemoryStorageBackend, db_session
    ):
        await self._doc_in(client, alice)
        await self._doc_in(client, alice)
        keys = set(storage.keys())
        resp = await call(
            client,
            alice,
            "DELETE",
            "/users/me",
            json={"password": PASSWORD, "confirmation": "delete my account"},
        )
        assert resp.status_code == 200, resp.text
        rows = (await db_session.execute(select(StorageCleanup))).scalars().all()
        assert {r.storage_key for r in rows} == keys
        assert {r.reason for r in rows} == {"account_deleted"}
        assert (await db_session.execute(select(func.count(Document.id)))).scalar_one() == 0

    async def test_export_has_document_metadata_only(
        self, client: AsyncClient, alice: Actor, storage: InMemoryStorageBackend
    ):
        doc = await self._doc_in(client, alice)
        resp = await call(client, alice, "GET", "/users/me/export")
        assert resp.status_code == 200, resp.text
        exported = resp.json()
        payload = exported.get("data", exported)
        docs = payload["documents"]
        assert [d["id"] for d in docs] == [doc["id"]]
        assert set(docs[0]) >= {"display_name", "file_type", "file_size"}
        text = resp.text
        assert "storage_key" not in text and "checksum" not in text and "original.pdf" not in text
