"""Streaming (SSE), cancellation, regenerate, usage records, quotas and recovery (M3).

Everything runs on the fake provider. `httpx.ASGITransport` buffers a response, so frame ordering
is checked on the buffered body, and a true disconnect is driven with a raw ASGI call.
"""

import asyncio
import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from structlog.testing import capture_logs

from app.ai.errors import LLMUnavailableError
from app.ai.orchestration import streaming
from app.ai.orchestration.recovery import sweep_stale_generations
from app.ai.orchestration.streaming import get_generation_registry, sse_event
from app.ai.providers.fake_provider import FakeProvider
from app.ai.usage import pricing
from app.core.config import get_settings
from app.main import app
from app.models.ai_usage_record import AiUsageRecord
from app.models.llm_provider import LLMModel
from app.models.message import Message
from tests.ai.conftest import AiHarness, call, new_conversation, send
from tests.conftest import _TestSessionLocal
from tests.test_closeout_users_config import Actor

Frame = tuple[str, Any]


def parse_sse(body: str) -> list[Frame]:
    frames: list[Frame] = []
    for block in body.split("\n\n"):
        if not block.strip() or block.startswith(":"):
            continue
        lines = dict(line.split(": ", 1) for line in block.split("\n"))
        frames.append((lines["event"], json.loads(lines["data"])))
    return frames


def names(frames: list[Frame]) -> list[str]:
    return [name for name, _ in frames]


async def stream(
    client: AsyncClient, who: Actor, cid: str, content: str = "hello", **kw: Any
) -> Any:
    return await send(client, who, cid, content, stream=True, **kw)


async def messages_in(client: AsyncClient, who: Actor, cid: str) -> list[dict[str, Any]]:
    resp = await call(client, who, "GET", f"/conversations/{cid}/messages")
    return list(resp.json()["data"])


async def usage_rows(user_id: uuid.UUID) -> list[AiUsageRecord]:
    async with _TestSessionLocal() as db:
        rows = await db.execute(
            select(AiUsageRecord)
            .where(AiUsageRecord.user_id == user_id)
            .order_by(AiUsageRecord.created_at)
        )
        return list(rows.scalars())


async def wait_for(predicate: Callable[[], Any], timeout: float = 5.0) -> Any:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        value = await predicate()
        if value:
            return value
        await asyncio.sleep(0.02)
    raise AssertionError("condition not reached in time")


async def streaming_message_id(user_id: uuid.UUID) -> uuid.UUID | None:
    async with _TestSessionLocal() as db:
        return (
            await db.execute(
                select(Message.id).where(Message.user_id == user_id, Message.status == "streaming")
            )
        ).scalar_one_or_none()


# ── framing ───────────────────────────────────────────────────────────────────


class TestFraming:
    def test_frame_is_one_data_line_even_when_text_has_newlines(self) -> None:
        raw = sse_event("message.delta", {"delta": "a\n\nb: c\r\nevent: evil"}).decode()
        assert raw.endswith("\n\n") and raw.count("\n\n") == 1
        assert raw.splitlines()[0] == "event: message.delta"
        assert len([ln for ln in raw.split("\n") if ln.startswith("data: ")]) == 1
        assert parse_sse(raw) == [("message.delta", {"delta": "a\n\nb: c\r\nevent: evil"})]

    async def test_headers_and_media_type(
        self, client: AsyncClient, ai: AiHarness, alice: Actor
    ) -> None:
        cid = await new_conversation(client, alice)
        resp = await stream(client, alice, cid)
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        assert resp.headers["cache-control"] == "no-store"
        assert resp.headers["x-accel-buffering"] == "no"

    async def test_post_without_csrf_header_is_rejected(
        self, client: AsyncClient, ai: AiHarness, alice: Actor
    ) -> None:
        cid = await new_conversation(client, alice)
        resp = await client.post(
            f"/api/v1/ai/conversations/{cid}/messages",
            json={"content": "hi", "stream": True},
            cookies=alice.cookies,
        )
        assert resp.status_code == 403

    async def test_heartbeat_when_idle(
        self,
        client: AsyncClient,
        ai: AiHarness,
        fake: FakeProvider,
        alice: Actor,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(streaming, "SSE_HEARTBEAT_SECONDS", 0.05)
        fake.chunk_delay = 0.2
        fake.reply = "abcdefgh" * 2
        cid = await new_conversation(client, alice)
        resp = await stream(client, alice, cid)
        assert ": ping\n\n" in resp.text
        assert names(parse_sse(resp.text))[-1] == "message.completed"


# ── full stream ───────────────────────────────────────────────────────────────


class TestFullStream:
    async def test_event_order_content_and_usage(
        self, client: AsyncClient, ai: AiHarness, fake: FakeProvider, alice: Actor
    ) -> None:
        fake.reply = "The quick brown fox jumps over the lazy dog."
        cid = await new_conversation(client, alice)
        resp = await stream(client, alice, cid, "Tell me")
        frames = parse_sse(resp.text)
        order = names(frames)
        assert order[0] == "message.started"
        assert order[-2:] == ["usage.updated", "message.completed"]
        deltas = [d["delta"] for n, d in frames if n == "message.delta"]
        assert len(deltas) > 1 and "".join(deltas) == fake.reply  # ordered, none lost
        assert set(order[1:-2]) == {"message.delta"}

        stored = await messages_in(client, alice, cid)
        assert [(m["role"], m["status"]) for m in stored] == [
            ("user", "completed"),
            ("assistant", "completed"),
        ]
        assert stored[1]["content"] == fake.reply
        assert stored[1]["id"] == frames[0][1]["message_id"]

        rows = await usage_rows(alice.user.id)
        assert len(rows) == 1  # exactly one usage record, no duplicate assistant message
        row = rows[0]
        assert row.request_status == "success" and row.usage_source == "estimated"
        assert row.input_tokens and row.output_tokens and row.duration_ms is not None
        assert row.estimated_cost is None  # empty pricing registry: unknown, not zero

    async def test_title_is_set_from_first_stream(
        self, client: AsyncClient, ai: AiHarness, alice: Actor
    ) -> None:
        cid = await new_conversation(client, alice)
        await stream(client, alice, cid, "Explain eigenvectors")
        conv = (await call(client, alice, "GET", f"/conversations/{cid}")).json()["data"]
        assert conv["title"] == "Explain eigenvectors"

    async def test_followup_context_includes_streamed_answer(
        self, client: AsyncClient, ai: AiHarness, fake: FakeProvider, alice: Actor
    ) -> None:
        fake.reply = "first answer"
        cid = await new_conversation(client, alice)
        await stream(client, alice, cid, "q1")
        await stream(client, alice, cid, "q2")
        contents = [m.content for m in fake.calls[-1].messages]
        assert contents == ["q1", "first answer", "q2"]


# ── errors ────────────────────────────────────────────────────────────────────


class TestStreamErrors:
    async def test_error_before_stream_is_a_normal_http_error(
        self, client: AsyncClient, ai: AiHarness, alice: Actor
    ) -> None:
        missing = await stream(client, alice, str(uuid.uuid4()))
        assert missing.status_code == 404
        cid = await new_conversation(client, alice)
        blank = await stream(client, alice, cid, "  ")
        assert blank.status_code == 422
        ai.unconfigured()
        off = await stream(client, alice, cid)
        assert off.status_code == 503 and off.json()["error"]["code"] == "LLM_NOT_CONFIGURED"

    async def test_other_users_conversation_is_404(
        self, client: AsyncClient, ai: AiHarness, alice: Actor, bob: Actor
    ) -> None:
        cid = await new_conversation(client, alice)
        resp = await stream(client, bob, cid)
        assert resp.status_code == 404

    async def test_failure_mid_stream_keeps_partial_text_and_marks_failed(
        self, client: AsyncClient, ai: AiHarness, fake: FakeProvider, alice: Actor
    ) -> None:
        ai.configure(llm_max_retries=2)
        fake.reply = "0123456789" * 3
        fake.fail_after_chunks = 2
        cid = await new_conversation(client, alice)
        resp = await stream(client, alice, cid)
        frames = parse_sse(resp.text)
        assert names(frames)[-1] == "message.failed"
        assert frames[-1][1]["code"] == "LLM_UNAVAILABLE"
        assert "message.completed" not in names(frames)
        assert len(fake.calls) == 1  # no retry once a token was sent (D-50)

        assistant = (await messages_in(client, alice, cid))[1]
        assert assistant["status"] == "failed" and assistant["content"] == "0123456789012345"
        rows = await usage_rows(alice.user.id)
        assert [r.request_status for r in rows] == ["failed"]
        assert rows[0].error_code == "LLM_UNAVAILABLE"

    async def test_failure_before_first_token_is_retried(
        self, client: AsyncClient, ai: AiHarness, fake: FakeProvider, alice: Actor
    ) -> None:
        ai.configure(llm_max_retries=2)
        fake.fail_with = LLMUnavailableError()
        cid = await new_conversation(client, alice)
        resp = await stream(client, alice, cid)
        frames = parse_sse(resp.text)
        assert names(frames) == ["message.started", "message.failed"]
        assert len(fake.calls) == 3  # 1 try + 2 retries, all before any token
        assert [r.request_status for r in await usage_rows(alice.user.id)] == ["failed"]

    async def test_empty_stream_is_a_bad_response(
        self, client: AsyncClient, ai: AiHarness, fake: FakeProvider, alice: Actor
    ) -> None:
        fake.malformed = True
        cid = await new_conversation(client, alice)
        frames = parse_sse((await stream(client, alice, cid)).text)
        assert frames[-1][0] == "message.failed"
        assert frames[-1][1]["code"] == "LLM_BAD_RESPONSE"

    async def test_logs_never_contain_message_text(
        self, client: AsyncClient, ai: AiHarness, fake: FakeProvider, alice: Actor
    ) -> None:
        fake.reply = "SECRET-ANSWER-TEXT"
        cid = await new_conversation(client, alice)
        with capture_logs() as logs:
            await stream(client, alice, cid, "SECRET-QUESTION-TEXT")
        dump = json.dumps(logs, default=str)
        assert "SECRET-ANSWER-TEXT" not in dump and "SECRET-QUESTION-TEXT" not in dump


# ── cancel and disconnect ────────────────────────────────────────────────────


class TestCancel:
    async def test_cancel_endpoint_stops_generation_and_records_usage(
        self, client: AsyncClient, ai: AiHarness, fake: FakeProvider, alice: Actor
    ) -> None:
        fake.reply = "abcdefgh" * 50
        fake.chunk_delay = 0.05
        fake.delta_usage = True
        cid = await new_conversation(client, alice)
        task = asyncio.create_task(stream(client, alice, cid))
        mid = await wait_for(lambda: streaming_message_id(alice.user.id))
        await asyncio.sleep(0.2)
        resp = await call(client, alice, "POST", f"/conversations/{cid}/messages/{mid}/cancel")
        assert resp.status_code == 200 and resp.json()["data"]["status"] == "cancelled"
        frames = parse_sse((await task).text)
        assert names(frames)[-1] == "message.cancelled"
        assert "message.completed" not in names(frames)

        sent = fake.chunks_sent
        await asyncio.sleep(0.3)
        assert fake.chunks_sent == sent < 50  # the upstream call really stopped

        stored = (await messages_in(client, alice, cid))[1]
        assert stored["status"] == "cancelled" and 0 < len(stored["content"]) < len(fake.reply)
        rows = await usage_rows(alice.user.id)
        assert [r.request_status for r in rows] == ["cancelled"]
        assert rows[0].usage_source == "estimated" and rows[0].output_tokens  # real figures kept

    async def test_cancel_without_reported_usage_leaves_tokens_unknown(
        self, client: AsyncClient, ai: AiHarness, fake: FakeProvider, alice: Actor
    ) -> None:
        fake.reply = "abcdefgh" * 50
        fake.chunk_delay = 0.05
        cid = await new_conversation(client, alice)
        task = asyncio.create_task(stream(client, alice, cid))
        mid = await wait_for(lambda: streaming_message_id(alice.user.id))
        await asyncio.sleep(0.15)
        await call(client, alice, "POST", f"/conversations/{cid}/messages/{mid}/cancel")
        await task
        row = (await usage_rows(alice.user.id))[0]
        assert row.request_status == "cancelled"
        assert row.usage_source == "unavailable" and row.output_tokens is None

    async def test_cancelling_a_finished_message_is_harmless(
        self, client: AsyncClient, ai: AiHarness, alice: Actor
    ) -> None:
        cid = await new_conversation(client, alice)
        done = (await send(client, alice, cid)).json()["data"]["message"]["id"]
        resp = await call(client, alice, "POST", f"/conversations/{cid}/messages/{done}/cancel")
        assert resp.status_code == 200 and resp.json()["data"]["status"] == "completed"
        assert len(await usage_rows(alice.user.id)) == 1

    async def test_other_users_cannot_cancel(
        self, client: AsyncClient, ai: AiHarness, fake: FakeProvider, alice: Actor, bob: Actor
    ) -> None:
        fake.reply = "abcdefgh" * 40
        fake.chunk_delay = 0.05
        cid = await new_conversation(client, alice)
        task = asyncio.create_task(stream(client, alice, cid))
        mid = await wait_for(lambda: streaming_message_id(alice.user.id))
        resp = await call(client, bob, "POST", f"/conversations/{cid}/messages/{mid}/cancel")
        assert resp.status_code == 404
        still = await call(client, alice, "POST", f"/conversations/{cid}/messages/{mid}/cancel")
        assert still.status_code == 200
        await task

    async def test_disconnect_cancels_upstream_and_stores_outcome(
        self, client: AsyncClient, ai: AiHarness, fake: FakeProvider, alice: Actor
    ) -> None:
        fake.reply = "abcdefgh" * 60
        fake.chunk_delay = 0.05
        cid = await new_conversation(client, alice)
        body = json.dumps({"content": "hi", "stream": True}).encode()
        headers = [
            (b"content-type", b"application/json"),
            (b"host", b"test"),
            (b"x-csrf-token", alice.headers["X-CSRF-Token"].encode()),
            (
                b"cookie",
                "; ".join(f"{k}={v}" for k, v in alice.cookies.items()).encode(),
            ),
        ]
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "path": f"/api/v1/ai/conversations/{cid}/messages",
            "raw_path": f"/api/v1/ai/conversations/{cid}/messages".encode(),
            "query_string": b"",
            "root_path": "",
            "scheme": "http",
            "headers": headers,
            "client": ("127.0.0.1", 1),
            "server": ("test", 80),
        }
        disconnect = asyncio.Event()
        got_chunk = asyncio.Event()
        sent_body = False

        async def receive() -> dict[str, Any]:
            nonlocal sent_body
            if not sent_body:
                sent_body = True
                return {"type": "http.request", "body": body, "more_body": False}
            await disconnect.wait()
            return {"type": "http.disconnect"}

        async def send_(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.body" and message.get("body"):
                got_chunk.set()

        run = asyncio.create_task(app(scope, receive, send_))
        await asyncio.wait_for(got_chunk.wait(), 5)
        disconnect.set()
        await asyncio.wait_for(run, 5)

        async def cancelled() -> bool:
            rows = await usage_rows(alice.user.id)
            return bool(rows) and rows[0].request_status == "cancelled"

        await wait_for(cancelled)
        sent = fake.chunks_sent
        await asyncio.sleep(0.3)
        assert fake.chunks_sent == sent < 60
        assistant = (await messages_in(client, alice, cid))[1]
        assert assistant["status"] == "cancelled"
        assert get_generation_registry().active_ids() == set()


# ── concurrency and quotas ───────────────────────────────────────────────────


class TestConcurrencyAndQuotas:
    async def test_two_simultaneous_stream_sends_to_one_conversation(
        self, client: AsyncClient, ai: AiHarness, fake: FakeProvider, alice: Actor
    ) -> None:
        fake.chunk_delay = 0.05
        fake.reply = "abcdefgh" * 5
        cid = await new_conversation(client, alice)
        a, b = await asyncio.gather(stream(client, alice, cid), stream(client, alice, cid))
        assert sorted([a.status_code, b.status_code]) == [200, 409]
        loser = a if a.status_code == 409 else b
        assert loser.json()["error"]["code"] == "AI_GENERATION_IN_PROGRESS"
        stored = await messages_in(client, alice, cid)
        assert [m["role"] for m in stored] == ["user", "assistant"]
        assert len(await usage_rows(alice.user.id)) == 1

    async def test_active_cap_is_429_with_retry_after(
        self, client: AsyncClient, ai: AiHarness, fake: FakeProvider, alice: Actor
    ) -> None:
        ai.configure(ai_max_active_generations_per_user=1)
        fake.chunk_delay = 0.05
        fake.reply = "abcdefgh" * 10
        a = await new_conversation(client, alice)
        b = await new_conversation(client, alice)
        first = asyncio.create_task(stream(client, alice, a))
        await wait_for(lambda: streaming_message_id(alice.user.id))
        second = await stream(client, alice, b)
        assert second.status_code == 429
        assert second.json()["error"]["code"] == "AI_QUOTA_EXCEEDED"
        assert int(second.headers["retry-after"]) >= 1
        assert (await first).status_code == 200
        assert (await stream(client, alice, b)).status_code == 200  # free again

    async def test_daily_request_quota_counts_regenerate(
        self, client: AsyncClient, ai: AiHarness, alice: Actor
    ) -> None:
        ai.configure(ai_daily_message_quota=2)
        cid = await new_conversation(client, alice)
        first = await stream(client, alice, cid)
        mid = parse_sse(first.text)[0][1]["message_id"]
        regen = await call(
            client,
            alice,
            "POST",
            f"/conversations/{cid}/messages/{mid}/regenerate",
            json={"stream": True},
        )
        assert regen.status_code == 200
        blocked = await stream(client, alice, cid)
        assert blocked.status_code == 429
        assert blocked.json()["error"]["code"] == "AI_QUOTA_EXCEEDED"
        assert blocked.headers.get("retry-after")

    async def test_daily_token_quota(
        self, client: AsyncClient, ai: AiHarness, alice: Actor
    ) -> None:
        ai.configure(ai_daily_token_quota=5)
        cid = await new_conversation(client, alice)
        assert (await stream(client, alice, cid)).status_code == 200
        blocked = await stream(client, alice, cid)
        assert blocked.status_code == 429 and blocked.headers.get("retry-after")

    async def test_quota_is_per_user(
        self, client: AsyncClient, ai: AiHarness, alice: Actor, bob: Actor
    ) -> None:
        ai.configure(ai_daily_message_quota=1)
        a = await new_conversation(client, alice)
        b = await new_conversation(client, bob)
        assert (await stream(client, alice, a)).status_code == 200
        assert (await stream(client, alice, a)).status_code == 429
        assert (await stream(client, bob, b)).status_code == 200


# ── regenerate ───────────────────────────────────────────────────────────────


async def regenerate(client: AsyncClient, who: Actor, cid: str, mid: str, **body: Any) -> Any:
    return await call(
        client, who, "POST", f"/conversations/{cid}/messages/{mid}/regenerate", json=body
    )


class TestRegenerate:
    async def test_supersedes_old_answer_and_context_excludes_it(
        self, client: AsyncClient, ai: AiHarness, fake: FakeProvider, alice: Actor
    ) -> None:
        fake.reply = "old answer"
        cid = await new_conversation(client, alice)
        old = (await send(client, alice, cid, "question")).json()["data"]["message"]["id"]
        fake.reply = "new answer"
        resp = await regenerate(client, alice, cid, old, stream=False)
        assert resp.status_code == 201
        new = resp.json()["data"]["message"]
        assert new["content"] == "new answer" and new["id"] != old
        assert new["regenerates_message_id"] == old
        assert [m.content for m in fake.calls[-1].messages] == ["question"]

        stored = {m["id"]: m for m in await messages_in(client, alice, cid)}
        assert stored[old]["superseded_at"] is not None
        assert stored[new["id"]]["superseded_at"] is None

        fake.reply = "after"
        await send(client, alice, cid, "follow-up")
        assert [m.content for m in fake.calls[-1].messages] == [
            "question",
            "new answer",
            "follow-up",
        ]

    async def test_streamed_regenerate(
        self, client: AsyncClient, ai: AiHarness, fake: FakeProvider, alice: Actor
    ) -> None:
        cid = await new_conversation(client, alice)
        old = (await send(client, alice, cid, "q")).json()["data"]["message"]["id"]
        fake.reply = "streamed again"
        resp = await regenerate(client, alice, cid, old, stream=True)
        frames = parse_sse(resp.text)
        assert names(frames)[0] == "message.started" and names(frames)[-1] == "message.completed"
        assert len(await usage_rows(alice.user.id)) == 2

    async def test_only_latest_answer_can_be_regenerated(
        self, client: AsyncClient, ai: AiHarness, alice: Actor
    ) -> None:
        cid = await new_conversation(client, alice)
        first = (await send(client, alice, cid, "q1")).json()["data"]["message"]["id"]
        await send(client, alice, cid, "q2")
        resp = await regenerate(client, alice, cid, first, stream=False)
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "AI_REGENERATE_NOT_ALLOWED"

    async def test_repeated_clicks_make_one_new_attempt(
        self, client: AsyncClient, ai: AiHarness, fake: FakeProvider, alice: Actor
    ) -> None:
        cid = await new_conversation(client, alice)
        old = (await send(client, alice, cid, "q")).json()["data"]["message"]["id"]
        fake.chunk_delay = 0.05
        fake.reply = "abcdefgh" * 5
        a, b = await asyncio.gather(
            regenerate(client, alice, cid, old, stream=True),
            regenerate(client, alice, cid, old, stream=True),
        )
        assert sorted([a.status_code, b.status_code]) == [200, 409]
        live = [m for m in await messages_in(client, alice, cid) if m["superseded_at"] is None]
        assert [m["role"] for m in live] == ["user", "assistant"]

    async def test_failed_answer_can_be_regenerated(
        self, client: AsyncClient, ai: AiHarness, fake: FakeProvider, alice: Actor
    ) -> None:
        ai.configure(llm_max_retries=0)
        fake.fail_with = LLMUnavailableError()
        cid = await new_conversation(client, alice)
        failed = await send(client, alice, cid, "q")
        assert failed.status_code == 503
        bad = next(m for m in await messages_in(client, alice, cid) if m["role"] == "assistant")
        fake.fail_with = None
        resp = await regenerate(client, alice, cid, bad["id"], stream=False)
        assert resp.status_code == 201 and resp.json()["data"]["message"]["status"] == "completed"

    async def test_cross_user_and_wrong_target_are_404(
        self, client: AsyncClient, ai: AiHarness, alice: Actor, bob: Actor
    ) -> None:
        cid = await new_conversation(client, alice)
        data = (await send(client, alice, cid, "q")).json()["data"]
        assert (await regenerate(client, bob, cid, data["message"]["id"])).status_code == 404
        user_msg = data["user_message"]["id"]
        assert (await regenerate(client, alice, cid, user_msg)).status_code == 404
        assert (await regenerate(client, alice, cid, str(uuid.uuid4()))).status_code == 404


# ── recovery ─────────────────────────────────────────────────────────────────


class TestRecovery:
    async def _stuck(self, client: AsyncClient, alice: Actor, age_seconds: int) -> uuid.UUID:
        cid = await new_conversation(client, alice)
        data = (await send(client, alice, cid, "q")).json()["data"]
        mid = uuid.UUID(data["message"]["id"])
        async with _TestSessionLocal() as db:
            await db.execute(
                update(Message)
                .where(Message.id == mid)
                .values(
                    status="streaming",
                    updated_at=datetime.now(UTC) - timedelta(seconds=age_seconds),
                )
            )
            await db.commit()
        return mid

    async def test_stale_streaming_row_is_failed_with_usage_row(
        self, client: AsyncClient, ai: AiHarness, alice: Actor
    ) -> None:
        mid = await self._stuck(client, alice, 10_000)
        before = len(await usage_rows(alice.user.id))
        assert await sweep_stale_generations(_TestSessionLocal, get_settings()) == 1
        async with _TestSessionLocal() as db:
            row = (await db.execute(select(Message).where(Message.id == mid))).scalar_one()
            assert row.status == "failed" and row.error_code == "LLM_UNAVAILABLE"
        rows = await usage_rows(alice.user.id)
        assert len(rows) == before + 1 and rows[-1].request_status == "failed"
        assert await sweep_stale_generations(_TestSessionLocal, get_settings()) == 0

    async def test_fresh_and_registered_rows_are_untouched(
        self, client: AsyncClient, ai: AiHarness, alice: Actor
    ) -> None:
        fresh = await self._stuck(client, alice, 1)
        assert await sweep_stale_generations(_TestSessionLocal, get_settings()) == 0
        old = await self._stuck(client, alice, 10_000)
        handle = streaming.GenerationHandle(message_id=old, user_id=alice.user.id)
        get_generation_registry().register(handle)
        assert await sweep_stale_generations(_TestSessionLocal, get_settings()) == 0
        async with _TestSessionLocal() as db:
            for mid in (fresh, old):
                row = (await db.execute(select(Message).where(Message.id == mid))).scalar_one()
                assert row.status == "streaming"


# ── usage endpoints ──────────────────────────────────────────────────────────


class TestUsageEndpoints:
    async def test_each_outcome_is_listed_and_filterable(
        self, client: AsyncClient, ai: AiHarness, fake: FakeProvider, alice: Actor
    ) -> None:
        ai.configure(llm_max_retries=0)
        cid = await new_conversation(client, alice)
        await send(client, alice, cid, "ok")
        fake.fail_with = LLMUnavailableError()
        await send(client, alice, cid, "bad")
        fake.fail_with = None
        listing = (await call(client, alice, "GET", "/usage")).json()
        assert listing["total"] == 2
        assert {r["request_status"] for r in listing["data"]} == {"success", "failed"}
        only = (await call(client, alice, "GET", "/usage?status=failed")).json()
        assert [r["request_status"] for r in only["data"]] == ["failed"]
        page = (await call(client, alice, "GET", "/usage?limit=1&offset=1")).json()
        assert len(page["data"]) == 1 and page["total"] == 2
        assert (await call(client, alice, "GET", "/usage?limit=5000")).status_code == 422
        assert (await call(client, alice, "GET", "/usage?status=bogus")).status_code == 422

    async def test_summary_treats_unknown_as_unknown(
        self, client: AsyncClient, ai: AiHarness, fake: FakeProvider, alice: Actor
    ) -> None:
        ai.configure(llm_max_retries=0)
        cid = await new_conversation(client, alice)
        await send(client, alice, cid, "ok")
        fake.report_usage = False
        await send(client, alice, cid, "no usage reported")
        data = (await call(client, alice, "GET", "/usage/summary")).json()["data"]
        assert data["requests"] == 2 and data["token_known_requests"] == 1
        assert data["cost_known_requests"] == 0 and data["cost_by_currency"] == []
        assert data["total_tokens"] == data["input_tokens"] + data["output_tokens"] > 0

    async def test_known_price_produces_cost(
        self,
        client: AsyncClient,
        ai: AiHarness,
        alice: Actor,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from datetime import date
        from decimal import Decimal

        cid = await new_conversation(client, alice)
        await send(client, alice, cid, "unpriced")  # also syncs the catalogue
        async with _TestSessionLocal() as db:
            provider_model = (
                (await db.execute(select(LLMModel.provider_model_id))).scalars().first()
            )
        assert provider_model is not None
        monkeypatch.setattr(
            pricing,
            "PRICES",
            (
                pricing.PriceEntry(
                    "fake",
                    provider_model,
                    "test-1",
                    Decimal("1000000"),
                    Decimal("1000000"),
                    "USD",
                    "https://example.invalid",
                    date(2026, 1, 1),
                ),
            ),
        )
        await send(client, alice, cid, "priced")
        data = (await call(client, alice, "GET", "/usage/summary")).json()["data"]
        assert (
            data["requests"] == 2 and data["cost_known_requests"] == 1
        )  # unknown is not summed as 0
        assert data["cost_by_currency"][0]["currency"] == "USD"

    async def test_by_model_and_window(
        self, client: AsyncClient, ai: AiHarness, alice: Actor
    ) -> None:
        cid = await new_conversation(client, alice)
        await send(client, alice, cid, "a")
        await send(client, alice, cid, "b")
        grouped = (await call(client, alice, "GET", "/usage/by-model")).json()
        assert len(grouped["data"]) == 1 and grouped["data"][0]["requests"] == 2
        assert (await call(client, alice, "GET", "/usage/summary?days=0")).status_code == 422
        assert (await call(client, alice, "GET", "/usage/summary?days=91")).status_code == 422
        async with _TestSessionLocal() as db:
            await db.execute(
                update(AiUsageRecord).values(created_at=datetime.now(UTC) - timedelta(days=5))
            )
            await db.commit()
        recent = (await call(client, alice, "GET", "/usage/summary?days=1")).json()["data"]
        assert recent["requests"] == 0
        wide = (await call(client, alice, "GET", "/usage/summary?days=30")).json()["data"]
        assert wide["requests"] == 2

    async def test_usage_is_scoped_to_the_caller(
        self, client: AsyncClient, ai: AiHarness, alice: Actor, bob: Actor
    ) -> None:
        cid = await new_conversation(client, alice)
        await send(client, alice, cid, "mine")
        for path in ("/usage", "/usage/summary", "/usage/by-model"):
            body = (await call(client, bob, "GET", path)).json()
            payload = body["data"]
            if isinstance(payload, list):
                assert payload == []
            else:
                assert payload["requests"] == 0

    async def test_requires_authentication(self, client: AsyncClient, ai: AiHarness) -> None:
        for path in ("/usage", "/usage/summary", "/usage/by-model"):
            assert (await client.get(f"/api/v1/ai{path}")).status_code == 401
