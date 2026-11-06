"""Server-sent events for streamed generations (D-44, D-45, AI_ARCHITECTURE.md section 12).

Design: the generation runs as its own asyncio task with its own database session and pushes
pre-framed events into a queue. The HTTP response only drains that queue. So:

- a client disconnect (the response generator is cancelled/closed) cancels the TASK, which stops the
  upstream provider call and then stores the outcome in a shielded cleanup, whatever the socket did;
- the explicit cancel endpoint takes the same path through the in-process registry;
- partial content is flushed to the row while streaming, so a crash keeps what was produced.

The registry is per process (D-45). Message text is never logged here (D-51).
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.errors import AiError, LLMBadResponseError, LLMError
from app.ai.orchestration.context import ContextResult
from app.ai.orchestration.runtime import AiRuntime
from app.ai.orchestration.service import AiService, Prepared
from app.ai.types import LLMResponse, StreamDelta, StreamEnd, Usage
from app.core.logging import get_logger

logger = get_logger(__name__)

SSE_HEARTBEAT_SECONDS = 15.0
FLUSH_SECONDS = 2.0
FLUSH_BYTES = 1024
CANCEL_WAIT_SECONDS = 5.0

SSE_HEADERS = {
    "Cache-Control": "no-store",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}
SSE_PING = b": ping\n\n"


def sse_event(event: str, data: dict[str, Any]) -> bytes:
    """One SSE frame. `json.dumps` escapes newlines, so model text can never break the framing."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode()


# ── registry ─────────────────────────────────────────────────────────────────


@dataclass
class GenerationHandle:
    message_id: uuid.UUID
    user_id: uuid.UUID
    task: asyncio.Task[None] | None = None
    done: asyncio.Event = field(default_factory=asyncio.Event)
    cancel_reason: str | None = None

    def request_cancel(self, reason: str) -> None:
        if self.cancel_reason is None:
            self.cancel_reason = reason
        if self.task is not None and not self.task.done():
            self.task.cancel()


class GenerationRegistry:
    """Running generations in THIS process, keyed by assistant message id."""

    def __init__(self) -> None:
        self._handles: dict[uuid.UUID, GenerationHandle] = {}

    def register(self, handle: GenerationHandle) -> None:
        self._handles[handle.message_id] = handle

    def remove(self, message_id: uuid.UUID) -> None:
        self._handles.pop(message_id, None)

    def get(self, message_id: uuid.UUID, user_id: uuid.UUID) -> GenerationHandle | None:
        handle = self._handles.get(message_id)
        return handle if handle is not None and handle.user_id == user_id else None

    def active_ids(self) -> set[uuid.UUID]:
        return set(self._handles)

    def clear(self) -> None:
        self._handles.clear()


_registry = GenerationRegistry()


def get_generation_registry() -> GenerationRegistry:
    return _registry


# ── runner ───────────────────────────────────────────────────────────────────

Emit = Callable[[bytes], None]


class StreamRunner:
    def __init__(
        self,
        runtime: AiRuntime,
        session_factory: async_sessionmaker[AsyncSession],
        registry: GenerationRegistry | None = None,
    ) -> None:
        self._runtime = runtime
        self._factory = session_factory
        self._registry = registry or get_generation_registry()

    async def events(
        self, snapshot: Prepared, context: ContextResult, started: float
    ) -> AsyncIterator[bytes]:
        """The response body: frames from the generation task, plus a heartbeat while idle."""
        queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        handle = GenerationHandle(
            message_id=snapshot.assistant_message.id, user_id=snapshot.conversation.user_id
        )
        handle.task = asyncio.create_task(self._run(snapshot, context, queue, handle, started))
        self._registry.register(handle)
        try:
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=SSE_HEARTBEAT_SECONDS)
                except TimeoutError:
                    yield SSE_PING
                    continue
                if item is None:
                    return
                yield item
        finally:
            # Reached on normal end, on client disconnect (cancel/close) and on server shutdown.
            if not handle.done.is_set():
                handle.request_cancel("disconnect")

    async def _run(
        self,
        snapshot: Prepared,
        context: ContextResult,
        queue: asyncio.Queue[bytes | None],
        handle: GenerationHandle,
        started: float,
    ) -> None:
        emit: Emit = queue.put_nowait
        try:
            async with self._factory() as db:
                service = AiService(db, self._runtime)
                prepared = await service.reload_prepared(snapshot)
                if prepared is None:  # the conversation was deleted before we began
                    emit(self._failed(handle.message_id, LLMBadResponseError()))
                    return
                await self._generate(service, db, prepared, context, emit, handle, started)
        except Exception:
            logger.exception("ai_stream_task_crashed", message_id=str(handle.message_id))
            emit(self._failed(handle.message_id, LLMBadResponseError()))
        finally:
            self._registry.remove(handle.message_id)
            handle.done.set()
            emit(None)  # type: ignore[arg-type]  # sentinel: end of stream

    @staticmethod
    def _failed(message_id: uuid.UUID, error: AiError) -> bytes:
        return sse_event(
            "message.failed",
            {"message_id": str(message_id), "code": error.code, "message": error.user_message},
        )

    async def _generate(
        self,
        service: AiService,
        db: AsyncSession,
        prepared: Prepared,
        context: ContextResult,
        emit: Emit,
        handle: GenerationHandle,
        started: float,
    ) -> None:
        assistant = prepared.assistant_message
        message_id = str(assistant.id)
        request = service.make_request(prepared, context.system_prompt, context.messages)
        parts: list[str] = []
        pending_bytes = 0
        last_flush = time.monotonic()
        usage: Usage | None = None
        end: StreamEnd | None = None

        try:
            assistant.status = "streaming"
            await db.commit()
            emit(
                sse_event(
                    "message.started",
                    {
                        "message_id": message_id,
                        "user_message_id": str(prepared.user_message.id),
                        "conversation_id": str(prepared.conversation.id),
                        "model_id": prepared.model.internal_id,
                    },
                )
            )
            async for event in service.stream_with_retries(request):
                if isinstance(event, StreamDelta):
                    parts.append(event.text)
                    pending_bytes += len(event.text.encode())
                    if event.usage is not None:
                        usage = event.usage
                    emit(sse_event("message.delta", {"delta": event.text}))
                    if (
                        pending_bytes >= FLUSH_BYTES
                        or time.monotonic() - last_flush >= FLUSH_SECONDS
                    ):
                        assistant.content = "".join(parts)
                        await db.commit()  # also refreshes updated_at for the stale sweeper
                        pending_bytes, last_flush = 0, time.monotonic()
                elif isinstance(event, StreamEnd):
                    end = event
            content = "".join(parts)
            if end is None or not content.strip():
                raise LLMBadResponseError()
            response = LLMResponse(
                content=content,
                model=request.model,
                finish_reason=end.finish_reason,
                usage=end.usage,
                provider_request_id=end.provider_request_id,
            )
            result = await service.finalize_success(prepared, response, started)
        except asyncio.CancelledError:
            reason = handle.cancel_reason or "cancelled"
            await asyncio.shield(
                service.finalize_failure(
                    prepared,
                    None,
                    started,
                    status="cancelled",
                    usage=usage,
                    partial_content="".join(parts),
                )
            )
            logger.info("ai_stream_cancelled", message_id=message_id, reason=reason)
            emit(sse_event("message.cancelled", {"message_id": message_id}))
            return
        except AiError as exc:
            await self._fail(
                service, prepared, exc, started, usage, parts, isinstance(exc, LLMError)
            )
            emit(self._failed(assistant.id, exc))
            return
        except Exception:
            error = LLMBadResponseError()
            await self._fail(service, prepared, error, started, usage, parts, True)
            emit(self._failed(assistant.id, error))
            return

        final = result.usage
        emit(
            sse_event(
                "usage.updated",
                {
                    "input_tokens": final.input_tokens,
                    "output_tokens": final.output_tokens,
                    "usage_source": final.source.value,
                },
            )
        )
        emit(
            sse_event(
                "message.completed",
                {"message_id": message_id, "finish_reason": end.finish_reason.value},
            )
        )

    @staticmethod
    async def _fail(
        service: AiService,
        prepared: Prepared,
        error: AiError,
        started: float,
        usage: Usage | None,
        parts: list[str],
        record_usage: bool,
    ) -> None:
        # Partial text stays on the row, but the status is `failed`: it never looks successful.
        await service.finalize_failure(
            prepared,
            error,
            started,
            usage=usage,
            partial_content="".join(parts),
            record_usage=record_usage,
        )
