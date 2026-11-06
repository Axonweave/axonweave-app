"""FakeProvider: tests and local UI development ONLY (D-60).

Deterministic and scriptable. It refuses to be created unless APP_ENV is `development` or
`testing`, and `LLM_PROVIDER=fake` must be set explicitly (it is never a fallback). Its token counts
are labelled `estimated`, and the API reports `kind == "test"` so the UI can badge it.
"""

from __future__ import annotations

import asyncio
import math
from collections.abc import AsyncIterator
from typing import Self

from app.ai.errors import LLMBadResponseError, LLMError, LLMNotConfiguredError, LLMUnavailableError
from app.ai.providers.base import LLMProvider
from app.ai.types import (
    Capabilities,
    FinishReason,
    LLMRequest,
    LLMResponse,
    ProviderModelInfo,
    StreamDelta,
    StreamEnd,
    StreamEvent,
    Usage,
    UsageSource,
)
from app.core.config import AppEnv, Settings

_ALLOWED_ENVS = (AppEnv.development, AppEnv.testing)


def _tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / 4))


class FakeProvider(LLMProvider):
    name = "fake"
    kind = "test"
    display_name = "Test provider (not a real AI)"
    capabilities = Capabilities(
        streaming=True,
        structured_output=False,
        usage_reporting=True,
        system_prompt=True,
        count_tokens=True,
        thinking_budget=False,
    )

    def __init__(self) -> None:
        # Knobs for tests. All default to a plain successful reply.
        self.reply: str | None = None  # fixed reply text; None = echo of the last user message
        self.chunk_size = 8
        self.chunk_delay = 0.0
        self.fail_with: LLMError | None = None  # raised before any output
        self.fail_after_chunks: int | None = None  # raise LLMUnavailableError mid-stream
        self.finish_reason = FinishReason.stop
        self.report_usage = True
        self.malformed = False  # return an empty body
        self.delta_usage = False  # attach cumulative usage to each delta (like Gemini chunks)
        self.chunks_sent = 0  # deltas actually yielded, to prove a cancelled stream stopped
        self.calls: list[LLMRequest] = []

    @classmethod
    def create(cls, settings: Settings) -> Self:
        if settings.app_env not in _ALLOWED_ENVS:
            raise LLMNotConfiguredError()
        provider = cls()
        provider.chunk_delay = settings.fake_llm_chunk_delay_seconds
        return provider

    def _text_for(self, request: LLMRequest) -> str:
        if self.reply is not None:
            return self.reply
        last = next((m.content for m in reversed(request.messages) if m.role == "user"), "")
        return f"Test reply to: {last[:200]}"

    def _usage(self, request: LLMRequest, output: str) -> Usage:
        if not self.report_usage:
            return Usage()
        prompt = (request.system_prompt or "") + "".join(m.content for m in request.messages)
        return Usage(
            input_tokens=_tokens(prompt),
            output_tokens=_tokens(output),
            source=UsageSource.estimated,
        )

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        if self.fail_with is not None:
            raise self.fail_with
        text = "" if self.malformed else self._text_for(request)
        if not text:
            raise LLMBadResponseError()
        return LLMResponse(
            content=text,
            model=request.model,
            finish_reason=self.finish_reason,
            usage=self._usage(request, text),
            provider_request_id="fake-request",
        )

    async def stream(self, request: LLMRequest) -> AsyncIterator[StreamEvent]:
        self.calls.append(request)
        if self.fail_with is not None:
            raise self.fail_with
        text = "" if self.malformed else self._text_for(request)
        if not text:
            raise LLMBadResponseError()
        sent = 0
        for start in range(0, len(text), self.chunk_size):
            if self.fail_after_chunks is not None and sent >= self.fail_after_chunks:
                raise LLMUnavailableError()
            if self.chunk_delay:
                await asyncio.sleep(self.chunk_delay)
            piece = text[start : start + self.chunk_size]
            seen = None
            if self.delta_usage and self.report_usage:
                seen = self._usage(request, text[: start + len(piece)])
            yield StreamDelta(piece, usage=seen)
            self.chunks_sent += 1
            sent += 1
        yield StreamEnd(
            finish_reason=self.finish_reason,
            usage=self._usage(request, text),
            provider_request_id="fake-request",
        )

    async def count_tokens(self, request: LLMRequest) -> int | None:
        return _tokens((request.system_prompt or "") + "".join(m.content for m in request.messages))

    async def list_models(self) -> list[ProviderModelInfo]:
        return [ProviderModelInfo("fake-model", "Fake model", ("generateContent",), 8000, 2000)]
