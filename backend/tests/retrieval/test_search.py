"""Phase 3 M4: scope resolution, keyword/semantic/hybrid search, isolation (D-73)."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.database.vector import EMBEDDING_COLUMN_DIMENSIONS
from app.embeddings.errors import EmbeddingUnavailableError
from app.embeddings.fake_provider import FAKE_MODEL, _vector
from app.main import app
from app.models.document import Document, DocumentVersion
from app.models.document_chunk import DocumentChunk
from app.models.folder import Folder
from app.models.subject import Subject
from app.models.workspace import Workspace
from app.modules.search.routes import get_query_embedder
from app.retrieval.scope import ResolvedScope, ScopeResolver
from app.retrieval.searcher import Searcher
from tests.conftest import _make_session, _make_user


class StubEmbedder:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    async def embed_query(self, user_id: uuid.UUID, text: str) -> tuple[list[float], str]:
        if self.fail:
            raise EmbeddingUnavailableError()
        return _vector(text, EMBEDDING_COLUMN_DIMENSIONS), FAKE_MODEL


class Actor:
    def __init__(self, user: Any, token: str, csrf: str, ws: Workspace, subject: Subject):
        self.user, self.ws, self.subject = user, ws, subject
        self.cookies = {"aw_session": token, "csrf_token": csrf}
        self.headers = {"X-CSRF-Token": csrf}


async def actor(db: AsyncSession, email: str) -> Actor:
    user = await _make_user(db, email=email)
    token, csrf = await _make_session(db, user)
    ws = Workspace(user_id=user.id, name="WS", workspace_type="personal_learning", is_default=False)
    db.add(ws)
    await db.flush()
    subject = Subject(workspace_id=ws.id, name="Subj")
    db.add(subject)
    await db.flush()
    await db.commit()
    return Actor(user, token, csrf, ws, subject)


async def add_doc(
    db: AsyncSession,
    who: Actor,
    name: str,
    texts: list[str],
    *,
    folder_id: uuid.UUID | None = None,
    status: str = "completed",
    archived: bool = False,
    model: str = FAKE_MODEL,
) -> Document:
    doc = Document(
        user_id=who.user.id,
        workspace_id=who.ws.id,
        subject_id=who.subject.id,
        folder_id=folder_id,
        display_name=name,
        original_filename=name + ".txt",
        file_type="txt",
        mime_type="text/plain",
        file_size=10,
        checksum="0" * 64,
        processing_status=status,
        active_version=1 if status == "completed" else None,
        latest_version=1,
        archived_at=datetime.now(UTC) if archived else None,
    )
    db.add(doc)
    await db.flush()
    version = DocumentVersion(
        document_id=doc.id,
        user_id=who.user.id,
        version_number=1,
        storage_key=f"k/{uuid.uuid4()}",
        file_size=10,
        checksum="0" * 64,
        processing_status=status,
    )
    db.add(version)
    await db.flush()
    for i, text in enumerate(texts):
        db.add(
            DocumentChunk(
                user_id=who.user.id,
                document_id=doc.id,
                document_version_id=version.id,
                workspace_id=who.ws.id,
                subject_id=who.subject.id,
                folder_id=folder_id,
                chunk_index=i,
                content=text,
                page_number=i + 1,
                token_count=len(text) // 4 + 1,
                char_count=len(text),
                embedding=_vector(text, EMBEDDING_COLUMN_DIMENSIONS),
                embedding_model=model,
                embedding_dimensions=EMBEDDING_COLUMN_DIMENSIONS,
                index_version=get_settings().embedding_index_version,
            )
        )
    await db.commit()
    return doc


PHOTO = "Photosynthesis converts light energy into chemical energy inside chloroplasts."
KREBS = "The Krebs cycle oxidises acetyl-CoA to carbon dioxide in mitochondria."
ROME = "The Roman Republic became an empire under Augustus after civil wars."


@pytest.fixture(autouse=True)
def _fake_vector_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    # The default is calibrated for real embeddings; hashed bag-of-words scores run lower.
    monkeypatch.setattr(get_settings(), "retrieval_min_vector_score", 0.1)


@pytest.fixture
async def alice(db_session: AsyncSession) -> Actor:
    return await actor(db_session, "alice-search@example.com")


@pytest.fixture
async def bob(db_session: AsyncSession) -> Actor:
    return await actor(db_session, "bob-search@example.com")


@pytest.fixture
def embedder() -> Iterator[StubEmbedder]:
    stub = StubEmbedder()
    app.dependency_overrides[get_query_embedder] = lambda: stub
    yield stub
    app.dependency_overrides.pop(get_query_embedder, None)


async def run(
    db: AsyncSession,
    who: Actor,
    query: str,
    mode: Any = "hybrid",
    *,
    scope: ResolvedScope | None = None,
) -> Any:
    scope = scope or await ScopeResolver(db).resolve(who.user.id, "all")
    return await Searcher(db, get_settings(), StubEmbedder()).search(scope, query, mode=mode)


class TestSearcher:
    async def test_keyword_semantic_hybrid_find_the_right_chunk(
        self, db_session: AsyncSession, alice: Actor
    ):
        await add_doc(db_session, alice, "bio", [PHOTO, KREBS])
        await add_doc(db_session, alice, "hist", [ROME])
        for mode in ("keyword", "semantic", "hybrid"):
            result = await run(db_session, alice, "photosynthesis chloroplasts light", mode)
            assert result.hits and result.hits[0].content == PHOTO, mode
            assert result.mode_used == mode and not result.degraded

    async def test_semantic_threshold_drops_unrelated(self, db_session: AsyncSession, alice: Actor):
        await add_doc(db_session, alice, "bio", [PHOTO])
        result = await run(db_session, alice, "quantum chromodynamics gluons", "semantic")
        assert result.hits == []

    async def test_degrades_to_keyword_when_embedder_fails(
        self, db_session: AsyncSession, alice: Actor
    ):
        await add_doc(db_session, alice, "bio", [PHOTO])
        scope = await ScopeResolver(db_session).resolve(alice.user.id, "all")
        result = await Searcher(db_session, get_settings(), StubEmbedder(fail=True)).search(
            scope, "photosynthesis", mode="hybrid"
        )
        assert result.degraded and result.mode_used == "keyword" and result.hits
        none = await Searcher(db_session, get_settings(), None).search(
            scope, "photosynthesis", mode="semantic"
        )
        assert none.degraded and none.mode_used == "keyword"

    async def test_other_users_chunks_never_returned(
        self, db_session: AsyncSession, alice: Actor, bob: Actor
    ):
        await add_doc(db_session, bob, "secret", [PHOTO])
        for mode in ("keyword", "semantic", "hybrid"):
            assert (await run(db_session, alice, "photosynthesis", mode)).hits == []

    async def test_inactive_documents_excluded(self, db_session: AsyncSession, alice: Actor):
        await add_doc(db_session, alice, "failed", [PHOTO], status="failed")
        await add_doc(db_session, alice, "archived", [PHOTO], archived=True)
        assert (await run(db_session, alice, "photosynthesis")).hits == []

    async def test_other_model_or_index_version_excluded(
        self, db_session: AsyncSession, alice: Actor
    ):
        await add_doc(db_session, alice, "old", [PHOTO], model="some-other-model")
        assert (await run(db_session, alice, "photosynthesis", "semantic")).hits == []

    async def test_token_budget_and_top_k(self, db_session: AsyncSession, alice: Actor):
        await add_doc(db_session, alice, "bio", [PHOTO + f" variant {i}" for i in range(6)])
        scope = await ScopeResolver(db_session).resolve(alice.user.id, "all")
        s = Searcher(db_session, get_settings(), StubEmbedder())
        assert len((await s.search(scope, "photosynthesis", top_k=3)).hits) == 3
        tiny = await s.search(scope, "photosynthesis", token_budget=1)
        assert len(tiny.hits) == 1  # always at least the best hit


class TestScopes:
    async def test_each_scope_kind(self, db_session: AsyncSession, alice: Actor):
        folder = Folder(subject_id=alice.subject.id, name="F")
        db_session.add(folder)
        await db_session.flush()
        child = Folder(subject_id=alice.subject.id, name="C", parent_folder_id=folder.id)
        db_session.add(child)
        await db_session.flush()
        await db_session.commit()
        in_child = await add_doc(db_session, alice, "child", [PHOTO], folder_id=child.id)
        loose = await add_doc(db_session, alice, "loose", [KREBS])
        r = ScopeResolver(db_session)
        uid = alice.user.id
        assert set((await r.resolve(uid, "all")).document_ids) == {in_child.id, loose.id}
        assert set((await r.resolve(uid, "workspace", alice.ws.id)).document_ids) == {
            in_child.id,
            loose.id,
        }
        assert len((await r.resolve(uid, "subject", alice.subject.id)).document_ids) == 2
        assert (await r.resolve(uid, "folder", folder.id)).document_ids == (in_child.id,)
        assert (await r.resolve(uid, "document", loose.id)).document_ids == (loose.id,)

    async def test_foreign_scope_ids_are_404(
        self, db_session: AsyncSession, alice: Actor, bob: Actor
    ):
        doc = await add_doc(db_session, bob, "b", [PHOTO])
        r = ScopeResolver(db_session)
        for kind, sid in (
            ("workspace", bob.ws.id),
            ("subject", bob.subject.id),
            ("document", doc.id),
            ("folder", uuid.uuid4()),
        ):
            with pytest.raises(Exception) as exc:
                await r.resolve(alice.user.id, kind, sid)  # type: ignore[arg-type]
            assert getattr(exc.value, "status_code", None) == 404

    def test_resolved_scope_cannot_be_forged(self):
        with pytest.raises(TypeError):
            ResolvedScope(uuid.uuid4(), (uuid.uuid4(),))


class TestSearchApi:
    async def test_requires_auth(self, client: AsyncClient):
        resp = await client.post("/api/v1/search", json={"query": "x"})
        assert resp.status_code == 401

    async def test_search_end_to_end(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, embedder: StubEmbedder
    ):
        doc = await add_doc(db_session, alice, "bio", [PHOTO, KREBS])
        resp = await client.post(
            "/api/v1/search",
            json={
                "query": "krebs cycle mitochondria",
                "scope": {"kind": "document", "id": str(doc.id)},
            },
            cookies=alice.cookies,
            headers=alice.headers,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["results"][0]["page_number"] == 2 and data["mode_used"] == "hybrid"
        assert "storage" not in resp.text

    async def test_foreign_scope_is_404_and_validation(
        self, client: AsyncClient, db_session: AsyncSession, alice: Actor, bob: Actor, embedder: Any
    ):
        doc = await add_doc(db_session, bob, "b", [PHOTO])
        kw: dict[str, Any] = {"cookies": alice.cookies, "headers": alice.headers}
        resp = await client.post(
            "/api/v1/search",
            json={"query": "x", "scope": {"kind": "document", "id": str(doc.id)}},
            **kw,
        )
        assert resp.status_code == 404
        for bad in (
            {"query": ""},
            {"query": "   "},
            {"query": "x" * 1001},
            {"query": "x", "mode": "nope"},
            {"query": "x", "scope": {"kind": "folder"}},
            {"query": "x", "scope": {"kind": "all", "id": str(doc.id)}},
        ):
            assert (await client.post("/api/v1/search", json=bad, **kw)).status_code == 422

    async def test_rate_limited(
        self, client: AsyncClient, alice: Actor, embedder: Any, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(get_settings(), "search_requests_per_minute_per_user", 2)
        codes = [
            (
                await client.post(
                    "/api/v1/search",
                    json={"query": "x"},
                    cookies=alice.cookies,
                    headers=alice.headers,
                )
            ).status_code
            for _ in range(3)
        ]
        assert codes == [200, 200, 429]
