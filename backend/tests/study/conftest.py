"""Fixtures for the study generation tests. FakeProvider only: no network, no cost."""

import json
import uuid
from collections.abc import Generator
from dataclasses import dataclass
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.model_registry import build_registry
from app.ai.orchestration.runtime import AiRuntime, get_ai_runtime
from app.ai.providers.fake_provider import FakeProvider
from app.core.rate_limit import get_rate_limiter
from app.main import app
from app.models.chapter import Chapter
from app.models.document import Document
from app.study import engine
from app.study.dispatch import get_generation_dispatcher
from app.study.engine import EngineDeps, run_generation
from tests.ai.test_provider_layer import make_settings
from tests.conftest import _TestSessionLocal
from tests.retrieval.test_search import Actor, actor, add_doc
from tests.test_closeout_users_config import _call

PHOTO = "Photosynthesis converts light energy into chemical energy inside chloroplasts."
KREBS = "The Krebs cycle oxidises acetyl-CoA to carbon dioxide in mitochondria."
ROME = "The Roman Republic became an empire under Augustus after civil wars."

GOOD = json.dumps(
    {
        "title": "Cell energy",
        "items": [
            {"text": "Chloroplasts capture light.", "difficulty": "easy", "source_refs": [1]},
            {
                "text": "Mitochondria run the Krebs cycle.",
                "difficulty": "medium",
                "source_refs": [2, 99],
            },
        ],
    }
)


class RecordingDispatcher:
    def __init__(self) -> None:
        self.sent: list[uuid.UUID] = []
        self.is_available = True

    def available(self) -> bool:
        return self.is_available

    def dispatch(self, job_id: uuid.UUID) -> bool:
        self.sent.append(job_id)
        return True


@dataclass
class Harness:
    provider: FakeProvider
    dispatcher: RecordingDispatcher
    runtime: AiRuntime

    def configure(self, **settings: Any) -> AiRuntime:
        base: dict[str, Any] = {
            "llm_provider": "fake",
            "study_cancel_poll_seconds": 0.02,
            "study_requests_per_minute_per_user": 1000,
            "study_daily_generation_quota": 100,
            "study_max_active_jobs_per_user": 50,
            "ai_daily_token_quota": 10_000_000,
        }
        cfg = make_settings(**{**base, **settings})
        self.runtime = AiRuntime(cfg, build_registry(cfg), lambda: self.provider)
        app.dependency_overrides[get_ai_runtime] = lambda: self.runtime
        return self.runtime

    def unconfigured(self) -> None:
        cfg = make_settings()
        self.runtime = AiRuntime(cfg, build_registry(cfg), lambda: self.provider)
        app.dependency_overrides[get_ai_runtime] = lambda: self.runtime

    async def run(self, job_id: str | uuid.UUID) -> str:
        return await run_generation(
            EngineDeps(_TestSessionLocal, self.runtime), uuid.UUID(str(job_id))
        )


@pytest.fixture
def study(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> Generator[Harness]:
    monkeypatch.setattr(engine, "RETRY_BASE_DELAY", 0.0)
    get_rate_limiter().reset()
    provider = FakeProvider()
    provider.reply = GOOD
    dispatcher = RecordingDispatcher()
    app.dependency_overrides[get_generation_dispatcher] = lambda: dispatcher
    harness = Harness(provider, dispatcher, None)  # type: ignore[arg-type]
    harness.configure()
    yield harness
    app.dependency_overrides.pop(get_generation_dispatcher, None)
    app.dependency_overrides.pop(get_ai_runtime, None)


@pytest.fixture
async def alice(db_session: AsyncSession) -> Actor:
    who = await actor(db_session, "alice-study@example.com")
    who.uid = who.user.id  # type: ignore[attr-defined]
    return who


@pytest.fixture
async def bob(db_session: AsyncSession) -> Actor:
    who = await actor(db_session, "bob-study@example.com")
    who.uid = who.user.id  # type: ignore[attr-defined]
    return who


async def two_docs(db: AsyncSession, who: Actor, name: str = "Biology") -> Document:
    return await add_doc(db, who, name, [PHOTO, KREBS])


async def post_generation(
    client: AsyncClient, who: Actor, source: dict[str, Any], **settings: Any
) -> Any:
    return await _call(
        client,
        who,
        "POST",
        "/study/generations",
        json={"generation_type": "echo", "source": source, "settings": settings},
    )


async def get_job(client: AsyncClient, who: Actor, job_id: str) -> dict[str, Any]:
    resp = await _call(client, who, "GET", f"/study/generations/{job_id}")
    assert resp.status_code == 200, resp.text
    data: dict[str, Any] = resp.json()["data"]
    return data


async def make_chapter(db: AsyncSession, who: Actor, docs: list[Document]) -> Chapter:
    chapter = Chapter(subject_id=who.subject.id, title="Ch 1")
    db.add(chapter)
    await db.flush()
    for doc in docs:
        doc.chapter_id = chapter.id
        db.add(doc)
    await db.commit()
    return chapter
