"""One real-provider RAG run through the API (Phase 3 M5). Prints metrics, never document or answer text.

Creates a throwaway user and document in the CURRENT database, indexes the document with the real
embedder, asks a grounded and an off-topic question through the HTTP API (real LLM), then deletes
the user (everything cascades). Needs LLM_PROVIDER, GEMINI_API_KEY, EMBEDDING_PROVIDER and
EMBEDDING_MODEL:

  docker compose exec -e EMBEDDING_PROVIDER=gemini -e EMBEDDING_MODEL=<id> backend \
      python scripts/rag_live_check.py
"""

import asyncio
import hashlib
import secrets
import sys
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402
from sqlalchemy import delete, select  # noqa: E402

from app.core.config import AppEnv, get_settings  # noqa: E402
from app.core.security import generate_token, hash_password, hash_token  # noqa: E402
from app.database.connection import AsyncSessionLocal  # noqa: E402
from app.embeddings.registry import get_embedding_provider  # noqa: E402
from app.embeddings.service import EmbeddingService  # noqa: E402
from app.ingestion.pipeline import PipelineDeps, run_job  # noqa: E402
from app.ingestion.version import PIPELINE_VERSION  # noqa: E402
from app.main import app  # noqa: E402
from app.models.session_model import Session  # noqa: E402
from app.models.subject import Subject  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.user_preferences import UserPreferences  # noqa: E402
from app.models.user_profile import UserProfile  # noqa: E402
from app.models.workspace import Workspace  # noqa: E402
from app.repositories.document_repository import DocumentRepository  # noqa: E402
from app.storage.keys import build_original_key  # noqa: E402
from app.storage.memory_backend import InMemoryStorageBackend  # noqa: E402

TEXT = (
    "Photosynthesis is the process by which plants, algae and some bacteria convert light energy "
    "into chemical energy stored in glucose. It takes place in chloroplasts.\n\n"
    "The light-dependent reactions occur in the thylakoid membranes. Chlorophyll absorbs light, "
    "water is split, oxygen is released, and ATP and NADPH are produced.\n\n"
    "The Calvin cycle occurs in the stroma. It uses ATP and NADPH to fix carbon dioxide into "
    "three-carbon sugars, which are later assembled into glucose.\n\n"
    "Cellular respiration is the opposite exchange: glucose and oxygen are used to make ATP, "
    "releasing carbon dioxide and water, mainly in mitochondria."
)


async def main() -> int:
    s = get_settings()
    if s.app_env == AppEnv.production or not s.embedding_provider or not s.llm_provider:
        print("Refusing: needs a non-production env with LLM and embedding providers configured.")
        return 2
    email = f"rag-live-{secrets.token_hex(4)}@example.com"
    storage = InMemoryStorageBackend(s.app_env)
    user_id: uuid.UUID | None = None
    try:
        async with AsyncSessionLocal() as db:
            user = User(
                email=email,
                password_hash=hash_password(secrets.token_urlsafe(16)),
                status="active",
                is_verified=True,
                email_verified_at=datetime.now(UTC),
                terms_accepted_at=datetime.now(UTC),
                terms_version="1.0",
            )
            db.add(user)
            await db.flush()
            user_id = user.id
            db.add(UserProfile(user_id=user.id, full_name="RAG live check"))
            prefs = UserPreferences(user_id=user.id)
            db.add(prefs)
            ws = Workspace(
                user_id=user.id, name="Live", workspace_type="personal_learning", is_default=True
            )
            db.add(ws)
            await db.flush()
            subject = Subject(workspace_id=ws.id, name="Biology")
            db.add(subject)
            token, csrf = generate_token(), generate_token()
            now = datetime.now(UTC)
            db.add(
                Session(
                    user_id=user.id,
                    session_token_hash=hash_token(token),
                    expires_at=now + timedelta(hours=1),
                    created_at=now,
                    last_used_at=now,
                )
            )
            data = TEXT.encode()
            document_id = uuid.uuid4()
            key = build_original_key(user.id, document_id, 1, "txt")

            async def body() -> AsyncIterator[bytes]:
                yield data

            await storage.put(key, body(), content_type="text/plain")
            _, job_id = await DocumentRepository(db).create_with_version_and_job(
                document_id=document_id,
                user_id=user.id,
                workspace_id=ws.id,
                subject_id=subject.id,
                folder_id=None,
                chapter_id=None,
                display_name="live-biology.txt",
                original_filename="live-biology.txt",
                file_type="txt",
                mime_type="text/plain",
                file_size=len(data),
                checksum=hashlib.sha256(data).hexdigest(),
                storage_key=key,
                pipeline_version=PIPELINE_VERSION,
            )
            await db.commit()

        embedder = EmbeddingService(AsyncSessionLocal, get_embedding_provider(s), s)
        outcome = await run_job(PipelineDeps(AsyncSessionLocal, storage, s, embedder), job_id)
        print(f"indexing outcome: {outcome}")

        cookies = {"aw_session": token, "csrf_token": csrf}
        headers = {"X-CSRF-Token": csrf}
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
            cookies=cookies,
            headers=headers,
            timeout=120,
        ) as client:

            async def post(path: str, **kw: object) -> httpx.Response:
                return await client.post(f"/api/v1{path}", **kw)  # type: ignore[arg-type]

            conv = await post(
                "/ai/conversations", json={"scope": {"kind": "document", "id": str(document_id)}}
            )
            cid = conv.json()["data"]["id"]
            print(f"create scoped conversation: {conv.status_code}")
            for label, question in (
                (
                    "grounded",
                    "Where do the light-dependent reactions take place, and what do they produce?",
                ),
                ("off-topic", "Who painted the Mona Lisa and in which year?"),
            ):
                resp = await post(f"/ai/conversations/{cid}/messages", json={"content": question})
                d = resp.json().get("data") or {}
                msg = d.get("message") or {}
                cites = d.get("citations") or []
                print(
                    f"{label}: http={resp.status_code} status={msg.get('status')} "
                    f"finish={msg.get('finish_reason')} "
                    f"answer_chars={len(msg.get('content') or '')} "
                    f"citations={[c['rank'] for c in cites]} "
                    f"tokens_in={msg.get('input_tokens')} tokens_out={msg.get('output_tokens')} "
                    f"prompt={msg.get('prompt_key')}"
                )
            stream = await post(
                f"/ai/conversations/{cid}/messages",
                json={"content": "What does the Calvin cycle do?", "stream": True},
            )
            events = [line[7:] for line in stream.text.split("\n") if line.startswith("event: ")]
            order_ok = events.index("message.citations") < events.index("message.delta")
            print(
                f"stream: http={stream.status_code} events={len(events)} "
                f"citations_before_first_delta={order_ok} last={events[-1]}"
            )
        return 0
    finally:
        if user_id is not None:
            async with AsyncSessionLocal() as db:
                await db.execute(delete(User).where(User.id == user_id))
                await db.commit()
            async with AsyncSessionLocal() as db:
                gone = (await db.execute(select(User.id).where(User.id == user_id))).first()
            print(f"cleanup: user removed={gone is None}")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
