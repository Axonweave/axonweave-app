"""Gemini adapter (official `google-genai` SDK). The ONLY module that imports it (D-57).

Notes (see AI_ARCHITECTURE.md section 13):
- system prompt goes in the SDK's system-instruction field, never into user text;
- our `assistant` role maps to Gemini's `model` role;
- blocked/safety finish reasons map to LLM_CONTENT_BLOCKED, max-tokens is a normal completion with
  finish_reason "length";
- usage comes from the response usage metadata; thought tokens are counted in output usage (D-40);
- vendor error text is never returned or logged, only mapped to a code.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import AsyncIterator
from typing import Any, Self

import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from app.ai.errors import (
    LLMAuthFailedError,
    LLMBadResponseError,
    LLMContentBlockedError,
    LLMContextTooLongError,
    LLMError,
    LLMInvalidModelError,
    LLMNotConfiguredError,
    LLMRateLimitedError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from app.ai.providers.base import LLMProvider
from app.ai.types import (
    Capabilities,
    FinishReason,
    LLMRequest,
    LLMResponse,
    ProviderModelInfo,
    Role,
    StreamDelta,
    StreamEnd,
    StreamEvent,
    Usage,
    UsageSource,
)
from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_ROLE_MAP = {Role.user: "user", Role.assistant: "model"}
_FILTERED = {"SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII", "IMAGE_SAFETY"}


def _enum_name(value: object) -> str:
    return str(getattr(value, "name", value) or "")


def map_finish_reason(value: object) -> FinishReason:
    name = _enum_name(value).upper()
    if name == "STOP":
        return FinishReason.stop
    if name == "MAX_TOKENS":
        return FinishReason.length
    if name in _FILTERED:
        return FinishReason.content_filter
    return FinishReason.other


def map_usage(meta: Any) -> Usage:
    """Usage from the response metadata. Missing fields stay None, never 0 (D-40)."""
    if meta is None:
        return Usage()
    prompt = getattr(meta, "prompt_token_count", None)
    candidates = getattr(meta, "candidates_token_count", None)
    thoughts = getattr(meta, "thoughts_token_count", None)
    output = (
        None if candidates is None and thoughts is None else (candidates or 0) + (thoughts or 0)
    )
    if prompt is None and output is None:
        return Usage()
    return Usage(
        input_tokens=prompt,
        output_tokens=output,
        reasoning_tokens=thoughts,
        source=UsageSource.provider_reported,
    )


def map_error(exc: BaseException) -> LLMError:
    """Vendor/transport exception -> our taxonomy. The vendor message is inspected, never kept."""
    if isinstance(exc, LLMError):
        return exc
    mapped = _map_error(exc)
    # Safe triage hint for operators: exception class, HTTP code and status word only. Never the
    # vendor message (it can echo request content) and never a key.
    status = getattr(exc, "status", None)
    mapped.diagnostic = (  # type: ignore[attr-defined]
        f"{type(exc).__name__} code={getattr(exc, 'code', None)} "
        f"status={status if isinstance(status, str) else None}"
    )
    return mapped


def _map_error(exc: BaseException) -> LLMError:
    if isinstance(exc, TimeoutError | asyncio.TimeoutError | httpx.TimeoutException):
        return LLMTimeoutError()
    if isinstance(exc, genai_errors.APIError):
        code = getattr(exc, "code", None)
        text = str(getattr(exc, "message", "") or "").lower()
        if code in (401, 403) or "api key" in text:
            return LLMAuthFailedError()
        if code == 404:
            return LLMInvalidModelError()
        if code == 429:
            return LLMRateLimitedError()
        if code == 400 and "token" in text and ("exceed" in text or "limit" in text):
            return LLMContextTooLongError()
        if code == 504:
            return LLMTimeoutError()
        if isinstance(code, int) and code >= 500:
            return LLMUnavailableError()
        return LLMBadResponseError()
    if isinstance(exc, httpx.TransportError | ConnectionError | OSError):
        return LLMUnavailableError()
    return LLMBadResponseError()


class GeminiProvider(LLMProvider):
    name = "gemini"
    display_name = "Google Gemini"
    capabilities = Capabilities(
        streaming=True,
        structured_output=False,  # reserved: not exposed in Phase 2
        usage_reporting=True,
        system_prompt=True,
        tool_calling=False,
        count_tokens=True,
        thinking_budget=True,
    )

    def __init__(self, client: Any) -> None:
        self._client = client

    @classmethod
    def create(cls, settings: Settings) -> Self:
        key = settings.gemini_api_key
        if key is None or not key.get_secret_value().strip():
            raise LLMNotConfiguredError()
        client = genai.Client(
            api_key=key.get_secret_value(),
            http_options=genai_types.HttpOptions(
                async_client_args={
                    "timeout": httpx.Timeout(
                        settings.llm_generation_timeout_seconds,
                        connect=settings.llm_connect_timeout_seconds,
                    )
                }
            ),
        )
        return cls(client)

    # ── request building ──────────────────────────────────────────────────────

    @staticmethod
    def _contents(request: LLMRequest) -> list[Any]:
        contents = []
        for message in request.messages:
            role = _ROLE_MAP.get(message.role)
            if role is None:  # system/tool messages do not belong in the turn list
                raise LLMBadResponseError()
            contents.append(
                genai_types.Content(role=role, parts=[genai_types.Part(text=message.content)])
            )
        return contents

    def _config(self, request: LLMRequest) -> Any:
        kwargs: dict[str, Any] = {"max_output_tokens": request.max_output_tokens}
        if request.system_prompt:
            kwargs["system_instruction"] = request.system_prompt
        if request.temperature is not None:
            kwargs["temperature"] = request.temperature
        if request.thinking_budget is not None:
            kwargs["thinking_config"] = genai_types.ThinkingConfig(
                thinking_budget=request.thinking_budget
            )
        kwargs["http_options"] = genai_types.HttpOptions(
            timeout=int(request.timeouts.generation * 1000)
        )
        return genai_types.GenerateContentConfig(**kwargs)

    # ── response parsing ──────────────────────────────────────────────────────

    @staticmethod
    def _check_prompt_block(response: Any) -> None:
        feedback = getattr(response, "prompt_feedback", None)
        if feedback is not None and getattr(feedback, "block_reason", None):
            raise LLMContentBlockedError()

    @staticmethod
    def _finish(response: Any) -> FinishReason | None:
        candidates = getattr(response, "candidates", None) or []
        if not candidates:
            return None
        reason = getattr(candidates[0], "finish_reason", None)
        return map_finish_reason(reason) if reason else None

    @staticmethod
    def _text(response: Any) -> str:
        try:
            return getattr(response, "text", None) or ""
        except Exception:  # SDK raises on non-text parts; treat as no text
            return ""

    # ── interface ─────────────────────────────────────────────────────────────

    async def generate(self, request: LLMRequest) -> LLMResponse:
        started = time.monotonic()
        try:
            response = await asyncio.wait_for(
                self._client.aio.models.generate_content(
                    model=request.model,
                    contents=self._contents(request),
                    config=self._config(request),
                ),
                timeout=min(request.timeouts.generation, request.timeouts.overall),
            )
            self._check_prompt_block(response)
        except BaseException as exc:
            if isinstance(exc, asyncio.CancelledError | KeyboardInterrupt):
                raise
            raise map_error(exc) from None

        text = self._text(response)
        finish = self._finish(response) or FinishReason.stop
        if not text:
            if finish is FinishReason.content_filter:
                raise LLMContentBlockedError()
            raise LLMBadResponseError()
        usage = map_usage(getattr(response, "usage_metadata", None))
        request_id = getattr(response, "response_id", None)
        logger.info(
            "llm_generate",
            provider=self.name,
            model=request.model,
            tag=request.request_tag,
            duration_ms=int((time.monotonic() - started) * 1000),
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            finish_reason=finish.value,
            provider_request_id=request_id,
        )
        return LLMResponse(
            content=text,
            model=request.model,
            finish_reason=finish,
            usage=usage,
            provider_request_id=request_id,
        )

    async def stream(self, request: LLMRequest) -> AsyncIterator[StreamEvent]:
        started = time.monotonic()
        deadline = started + request.timeouts.overall
        iterator: Any = None
        produced = False
        finish: FinishReason | None = None
        usage = Usage()
        request_id: str | None = None
        try:
            opened = await asyncio.wait_for(
                self._client.aio.models.generate_content_stream(
                    model=request.model,
                    contents=self._contents(request),
                    config=self._config(request),
                ),
                timeout=min(request.timeouts.generation, request.timeouts.overall),
            )
            iterator = opened.__aiter__()
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise LLMTimeoutError()
                try:
                    chunk = await asyncio.wait_for(
                        iterator.__anext__(),
                        timeout=min(request.timeouts.stream_inactivity, remaining),
                    )
                except StopAsyncIteration:
                    break
                self._check_prompt_block(chunk)
                request_id = getattr(chunk, "response_id", None) or request_id
                meta = getattr(chunk, "usage_metadata", None)
                if meta is not None:
                    usage = map_usage(meta)  # cumulative: keep the latest
                reason = self._finish(chunk)
                if reason is not None:
                    finish = reason
                text = self._text(chunk)
                if text:
                    produced = True
                    seen = (
                        usage
                        if meta is not None and usage.source is UsageSource.provider_reported
                        else None
                    )
                    yield StreamDelta(text, usage=seen)
        except BaseException as exc:
            if isinstance(exc, asyncio.CancelledError | GeneratorExit | KeyboardInterrupt):
                raise
            raise map_error(exc) from None
        finally:
            closer = getattr(iterator, "aclose", None)
            if closer is not None:
                with contextlib.suppress(Exception):  # closing must never mask the real outcome
                    await closer()

        finish = finish or FinishReason.stop
        if not produced:
            if finish is FinishReason.content_filter:
                raise LLMContentBlockedError()
            raise LLMBadResponseError()
        logger.info(
            "llm_stream",
            provider=self.name,
            model=request.model,
            tag=request.request_tag,
            duration_ms=int((time.monotonic() - started) * 1000),
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            finish_reason=finish.value,
            provider_request_id=request_id,
        )
        yield StreamEnd(finish_reason=finish, usage=usage, provider_request_id=request_id)

    async def count_tokens(self, request: LLMRequest) -> int | None:
        try:
            # The Gemini API rejects `system_instruction` in a count-tokens config, so the system
            # prompt is counted as a leading content block instead (an estimate, close enough).
            contents = self._contents(request)
            if request.system_prompt:
                contents.insert(
                    0,
                    genai_types.Content(
                        role="user", parts=[genai_types.Part(text=request.system_prompt)]
                    ),
                )
            result = await asyncio.wait_for(
                self._client.aio.models.count_tokens(model=request.model, contents=contents),
                timeout=min(request.timeouts.generation, request.timeouts.overall),
            )
        except BaseException as exc:
            if isinstance(exc, asyncio.CancelledError | KeyboardInterrupt):
                raise
            raise map_error(exc) from None
        total = getattr(result, "total_tokens", None)
        return int(total) if total is not None else None

    async def list_models(self) -> list[ProviderModelInfo]:
        models: list[ProviderModelInfo] = []
        try:
            pager = await self._client.aio.models.list()
            async for model in pager:
                name = str(getattr(model, "name", "") or "")
                models.append(
                    ProviderModelInfo(
                        provider_model_id=name.removeprefix("models/"),
                        display_name=getattr(model, "display_name", None),
                        supported_methods=tuple(getattr(model, "supported_actions", None) or ()),
                        input_token_limit=getattr(model, "input_token_limit", None),
                        output_token_limit=getattr(model, "output_token_limit", None),
                    )
                )
        except BaseException as exc:
            if isinstance(exc, asyncio.CancelledError | KeyboardInterrupt):
                raise
            raise map_error(exc) from None
        return models

    async def aclose(self) -> None:
        closer = getattr(getattr(self._client, "aio", None), "aclose", None)
        if closer is not None:
            await closer()
