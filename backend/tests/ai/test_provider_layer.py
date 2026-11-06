"""Provider layer tests: no network and no API key needed (fake provider + mocked SDK client)."""

import ast
import asyncio
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from google.genai import errors as genai_errors
from pydantic import SecretStr, ValidationError

from app.ai import errors as ai_errors
from app.ai.diagnostics import list_models_report, smoke_test_report
from app.ai.model_registry import build_registry
from app.ai.prompts.registry import PROMPTS, active_prompt
from app.ai.providers.fake_provider import FakeProvider
from app.ai.providers.gemini_provider import (
    GeminiProvider,
    map_error,
    map_finish_reason,
    map_usage,
)
from app.ai.providers.registry import get_provider, known_providers, reset_providers
from app.ai.types import (
    FinishReason,
    LLMMessage,
    LLMRequest,
    Role,
    StreamDelta,
    StreamEnd,
    TimeoutPolicy,
    Usage,
    UsageSource,
)
from app.ai.usage.pricing import PriceEntry, estimate_cost
from app.core.config import Settings

_BASE: dict[str, Any] = {
    "app_env": "development",
    "app_secret_key": "x" * 40,
    "database_url": "postgresql+psycopg://u:p@db:5432/app",
    "database_migration_url": "postgresql+psycopg://o:p@db:5432/app",
    # Explicit blanks: real environment variables override `_env_file=None`, so a developer with a
    # configured provider must not change what these tests see.
    "llm_provider": "",
    "llm_default_model": "",
    "llm_allowed_models": "",
    "gemini_api_key": None,
}
_PROD: dict[str, Any] = {
    **_BASE,
    "app_env": "production",
    "frontend_url": "https://app.example.com",
    "cookie_secure": True,
    "database_url": "postgresql+psycopg://u:realpass@db:5432/app",
    "database_migration_url": "postgresql+psycopg://o:realpass@db:5432/app",
}


def make_settings(**over: Any) -> Settings:
    return Settings(_env_file=None, **{**_BASE, **over})


def make_request(text: str = "hello", **over: Any) -> LLMRequest:
    fields: dict[str, Any] = {
        "model": "some-model",
        "system_prompt": "be brief",
        "messages": [LLMMessage(Role.user, text)],
        "max_output_tokens": 100,
        "timeouts": TimeoutPolicy(connect=1, generation=2, stream_inactivity=1, overall=3),
    }
    return LLMRequest(**{**fields, **over})


@pytest.fixture(autouse=True)
def _fresh_providers() -> Any:
    reset_providers()
    yield
    reset_providers()


# ── errors ───────────────────────────────────────────────────────────────────


def test_error_codes_are_unique_and_documented() -> None:
    codes = [
        cls.__dict__["code"]
        for cls in vars(ai_errors).values()
        if isinstance(cls, type)
        and issubclass(cls, ai_errors.AiError)
        and cls is not ai_errors.AiError  # base class; its default code is LLMBadResponseError's
        and cls.__dict__.get("code")
    ]
    assert len(codes) == len(set(codes))
    assert set(codes) <= ai_errors.ALL_ERROR_CODES


def test_http_exception_has_code_message_and_retry_after() -> None:
    exc = ai_errors.LLMRateLimitedError(retry_after=7).to_http_exception()
    assert exc.status_code == 429
    assert exc.detail["code"] == "LLM_RATE_LIMITED"
    assert exc.headers == {"Retry-After": "7"}


def test_not_configured_is_503() -> None:
    assert ai_errors.LLMNotConfiguredError().http_status == 503


# ── settings ─────────────────────────────────────────────────────────────────


def test_blank_optional_settings_become_none() -> None:
    s = make_settings(gemini_api_key="", llm_model_max_input_tokens="", llm_thinking_budget="")
    assert s.gemini_api_key is None
    assert s.llm_model_max_input_tokens is None
    assert s.llm_thinking_budget is None


def test_api_key_is_secret_and_never_in_repr() -> None:
    s = make_settings(gemini_api_key="real-looking-key-123")
    assert isinstance(s.gemini_api_key, SecretStr)
    assert "real-looking-key-123" not in repr(s)
    assert "real-looking-key-123" not in str(s.model_dump())


def test_fake_provider_rejected_in_production() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{**_PROD, "llm_provider": "fake"})


def test_placeholder_key_rejected_in_production() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            **{**_PROD, "llm_provider": "gemini", "gemini_api_key": "changeme"},
        )


# ── model registry ───────────────────────────────────────────────────────────


def test_unconfigured_registry_is_empty_and_resolves_to_not_configured() -> None:
    reg = build_registry(make_settings())
    assert not reg.configured
    with pytest.raises(ai_errors.LLMNotConfiguredError):
        reg.resolve(None)


def test_registry_default_and_allowed_models() -> None:
    reg = build_registry(
        make_settings(llm_provider="gemini", llm_default_model="m1", llm_allowed_models="m2, m3")
    )
    assert reg.default.provider_model_id == "m1"
    assert len(reg.enabled()) == 3
    assert reg.resolve("m-m2").provider_model_id == "m2"
    with pytest.raises(ai_errors.LLMInvalidModelError):
        reg.resolve("not-a-model")


def test_registry_public_dict_has_no_secrets() -> None:
    reg = build_registry(make_settings(llm_provider="fake"))
    data = reg.default.public_dict(is_default=True)
    assert set(data) == {
        "id",
        "display_name",
        "is_default",
        "capabilities",
        "max_input_tokens",
        "max_output_tokens",
    }


# ── provider registry ────────────────────────────────────────────────────────


def test_known_providers_and_unconfigured_gemini() -> None:
    assert {"gemini", "fake"} <= set(known_providers())
    with pytest.raises(ai_errors.LLMNotConfiguredError):
        get_provider("gemini", make_settings())


def test_fake_provider_refuses_production() -> None:
    settings = Settings(_env_file=None, **_PROD)
    with pytest.raises(ai_errors.LLMNotConfiguredError):
        FakeProvider.create(settings)


# ── fake provider ────────────────────────────────────────────────────────────


async def test_fake_generate_reports_estimated_usage() -> None:
    fake = FakeProvider.create(make_settings())
    fake.reply = "abcdefgh"
    resp = await fake.generate(make_request())
    assert resp.content == "abcdefgh"
    assert resp.usage.source is UsageSource.estimated
    assert len(fake.calls) == 1


async def test_fake_stream_chunks_then_end() -> None:
    fake = FakeProvider.create(make_settings())
    fake.reply = "x" * 20
    fake.chunk_size = 8
    events = [e async for e in fake.stream(make_request())]
    deltas = [e for e in events if isinstance(e, StreamDelta)]
    assert "".join(d.text for d in deltas) == "x" * 20
    assert isinstance(events[-1], StreamEnd)


async def test_fake_failure_modes() -> None:
    fake = FakeProvider.create(make_settings())
    fake.fail_with = ai_errors.LLMRateLimitedError()
    with pytest.raises(ai_errors.LLMRateLimitedError):
        await fake.generate(make_request())

    fake.fail_with = None
    fake.fail_after_chunks = 1
    fake.reply = "y" * 40
    seen: list[Any] = []
    with pytest.raises(ai_errors.LLMUnavailableError):
        async for event in fake.stream(make_request()):
            seen.append(event)
    assert seen and all(isinstance(e, StreamDelta) for e in seen)


# ── gemini mapping ───────────────────────────────────────────────────────────


def test_finish_reason_mapping() -> None:
    assert map_finish_reason(SimpleNamespace(name="STOP")) is FinishReason.stop
    assert map_finish_reason(SimpleNamespace(name="MAX_TOKENS")) is FinishReason.length
    assert map_finish_reason(SimpleNamespace(name="SAFETY")) is FinishReason.content_filter
    assert map_finish_reason(SimpleNamespace(name="SOMETHING_NEW")) is FinishReason.other


def test_usage_mapping_counts_thoughts_as_output_and_keeps_none() -> None:
    usage = map_usage(
        SimpleNamespace(prompt_token_count=10, candidates_token_count=5, thoughts_token_count=7)
    )
    assert (usage.input_tokens, usage.output_tokens, usage.reasoning_tokens) == (10, 12, 7)
    assert usage.source is UsageSource.provider_reported
    missing = map_usage(None)
    assert missing.input_tokens is None and missing.output_tokens is None


@pytest.mark.parametrize(
    ("code", "message", "expected"),
    [
        (401, "bad", ai_errors.LLMAuthFailedError),
        (403, "bad", ai_errors.LLMAuthFailedError),
        (400, "API key not valid", ai_errors.LLMAuthFailedError),
        (404, "model not found", ai_errors.LLMInvalidModelError),
        (429, "quota", ai_errors.LLMRateLimitedError),
        (400, "input token count exceeds the limit", ai_errors.LLMContextTooLongError),
        (504, "deadline", ai_errors.LLMTimeoutError),
        (503, "overloaded", ai_errors.LLMUnavailableError),
        (400, "something else", ai_errors.LLMBadResponseError),
    ],
)
def test_vendor_errors_map_to_taxonomy(code: int, message: str, expected: type) -> None:
    exc = genai_errors.APIError(code, {"error": {"message": message}})
    mapped = map_error(exc)
    assert isinstance(mapped, expected)
    assert message not in mapped.user_message  # vendor text is never passed on


def test_transport_errors_map() -> None:
    assert isinstance(map_error(TimeoutError()), ai_errors.LLMTimeoutError)
    assert isinstance(map_error(ConnectionError()), ai_errors.LLMUnavailableError)
    assert isinstance(map_error(ValueError("x")), ai_errors.LLMBadResponseError)


# ── gemini adapter with a mocked client ──────────────────────────────────────


def _response(text: str | None, finish: str = "STOP", **meta: int | None) -> Any:
    return SimpleNamespace(
        text=text,
        candidates=[SimpleNamespace(finish_reason=SimpleNamespace(name=finish))],
        usage_metadata=SimpleNamespace(
            prompt_token_count=meta.get("prompt", 4),
            candidates_token_count=meta.get("cand", 6),
            thoughts_token_count=meta.get("thoughts"),
        ),
        prompt_feedback=None,
        response_id="req-1",
    )


class _Models:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.result: Any = _response("hi there")
        self.chunks: list[Any] = []
        self.raises: BaseException | None = None
        self.delay = 0.0

    async def generate_content(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.raises:
            raise self.raises
        return self.result

    async def generate_content_stream(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.raises:
            raise self.raises
        chunks = self.chunks

        async def gen() -> Any:
            for chunk in chunks:
                yield chunk

        return gen()

    async def count_tokens(self, **kwargs: Any) -> Any:
        return SimpleNamespace(total_tokens=42)


def _adapter() -> tuple[GeminiProvider, _Models]:
    models = _Models()
    closed = SimpleNamespace(aclose=_noop)
    client = SimpleNamespace(aio=SimpleNamespace(models=models, aclose=closed.aclose))
    return GeminiProvider(client), models


async def _noop() -> None:
    return None


async def test_gemini_generate_sends_system_prompt_separately_and_maps_roles() -> None:
    provider, models = _adapter()
    request = make_request(
        messages=[
            LLMMessage(Role.user, "q1"),
            LLMMessage(Role.assistant, "a1"),
            LLMMessage(Role.user, "q2"),
        ]
    )
    resp = await provider.generate(request)
    assert resp.content == "hi there"
    assert resp.finish_reason is FinishReason.stop
    assert (resp.usage.input_tokens, resp.usage.output_tokens) == (4, 6)
    assert resp.provider_request_id == "req-1"
    call = models.calls[0]
    assert call["model"] == "some-model"
    assert [c.role for c in call["contents"]] == ["user", "model", "user"]
    assert call["config"].system_instruction == "be brief"
    assert all("be brief" not in p.text for c in call["contents"] for p in c.parts)


async def test_gemini_generate_empty_and_blocked() -> None:
    provider, models = _adapter()
    models.result = _response("", finish="STOP")
    with pytest.raises(ai_errors.LLMBadResponseError):
        await provider.generate(make_request())
    models.result = _response("", finish="SAFETY")
    with pytest.raises(ai_errors.LLMContentBlockedError):
        await provider.generate(make_request())


async def test_gemini_max_tokens_is_normal_completion() -> None:
    provider, models = _adapter()
    models.result = _response("cut off", finish="MAX_TOKENS")
    assert (await provider.generate(make_request())).finish_reason is FinishReason.length


async def test_gemini_generate_maps_vendor_error_without_leaking_text() -> None:
    provider, models = _adapter()
    models.raises = genai_errors.APIError(429, {"error": {"message": "secret-detail"}})
    with pytest.raises(ai_errors.LLMRateLimitedError) as info:
        await provider.generate(make_request())
    assert "secret-detail" not in info.value.user_message


async def test_gemini_generate_timeout() -> None:
    provider, models = _adapter()
    models.delay = 1.0
    request = make_request(
        timeouts=TimeoutPolicy(connect=1, generation=0.05, stream_inactivity=1, overall=0.05)
    )
    with pytest.raises(ai_errors.LLMTimeoutError):
        await provider.generate(request)


async def test_gemini_stream_yields_deltas_then_end_with_latest_usage() -> None:
    provider, models = _adapter()
    models.chunks = [_response("Hel", cand=1), _response("lo", finish="STOP", cand=2)]
    events = [e async for e in provider.stream(make_request())]
    assert "".join(e.text for e in events if isinstance(e, StreamDelta)) == "Hello"
    end = events[-1]
    assert isinstance(end, StreamEnd)
    assert end.usage.output_tokens == 2
    assert end.finish_reason is FinishReason.stop


async def test_gemini_stream_error_after_open() -> None:
    provider, models = _adapter()
    models.raises = genai_errors.APIError(503, {"error": {"message": "x"}})
    with pytest.raises(ai_errors.LLMUnavailableError):
        async for _ in provider.stream(make_request()):
            pass


async def test_gemini_count_tokens() -> None:
    provider, _ = _adapter()
    assert await provider.count_tokens(make_request()) == 42


def test_gemini_create_requires_key_and_never_exposes_it() -> None:
    with pytest.raises(ai_errors.LLMNotConfiguredError):
        GeminiProvider.create(make_settings())
    provider = GeminiProvider.create(make_settings(gemini_api_key="not-a-real-key"))
    assert "not-a-real-key" not in repr(vars(provider)).replace(repr(provider._client), "")


# ── pricing / prompts ────────────────────────────────────────────────────────


def test_cost_is_none_when_price_or_usage_unknown() -> None:
    usage = Usage(input_tokens=1000, output_tokens=2000, source=UsageSource.provider_reported)
    assert estimate_cost(None, usage) is None
    price = PriceEntry(
        "p",
        "m",
        "v1",
        Decimal("1"),
        None,
        "USD",
        "https://example.test",
        __import__("datetime").date(2026, 1, 1),
    )
    assert estimate_cost(price, usage) is None
    full = PriceEntry(
        "p", "m", "v1", Decimal("1"), Decimal("2"), "USD", "https://example.test", price.verified_on
    )
    assert estimate_cost(full, Usage()) is None
    assert estimate_cost(full, usage) == Decimal("0.005")


def test_prompt_catalogue_is_versioned_and_hashed() -> None:
    assert active_prompt("academic_tutor").version == 1
    assert len({(p.prompt_key, p.version) for p in PROMPTS}) == len(PROMPTS)
    assert len(PROMPTS[0].sha256) == 64


# ── diagnostics on the fake provider ─────────────────────────────────────────


async def test_smoke_test_report_on_fake_provider() -> None:
    report = await smoke_test_report(make_settings(llm_provider="fake"))
    assert "Result: OK" in report
    assert "Usage source: estimated" in report


async def test_smoke_test_stream_and_models_report_on_fake() -> None:
    settings = make_settings(llm_provider="fake")
    assert "Result: OK" in await smoke_test_report(settings, stream=True)
    assert "fake-model" in await list_models_report(settings)


async def test_smoke_test_unconfigured_raises() -> None:
    with pytest.raises(ai_errors.LLMNotConfiguredError):
        await smoke_test_report(make_settings())


# ── import boundary ──────────────────────────────────────────────────────────

_VENDOR_ROOTS = {"google", "openai", "anthropic", "vertexai", "cohere", "mistralai", "groq"}


def test_no_provider_sdk_imported_outside_providers_package() -> None:
    app_dir = Path(__file__).resolve().parents[2] / "app"
    allowed = app_dir / "ai" / "providers"
    offenders: list[str] = []
    for path in app_dir.rglob("*.py"):
        if allowed in path.parents:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module]
            if any(n.split(".")[0] in _VENDOR_ROOTS for n in names):
                offenders.append(f"{path.relative_to(app_dir)}: {names}")
    assert not offenders, offenders
