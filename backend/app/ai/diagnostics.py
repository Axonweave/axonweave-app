"""Operator diagnostics behind scripts/list_llm_models.py and scripts/llm_smoke_test.py.

Output is limited to model names, limits, token counts, finish reason and timings. It never prints
credentials, headers or the environment. The smoke test prints the model's reply to a fixed,
harmless prompt so an operator can see that a real round trip worked.
"""

from __future__ import annotations

import time

from app.ai.errors import LLMError, LLMNotConfiguredError
from app.ai.model_registry import build_registry
from app.ai.providers.registry import get_provider
from app.ai.types import LLMMessage, LLMRequest, Role, StreamDelta, StreamEnd, TimeoutPolicy
from app.core.config import Settings

SMOKE_PROMPT = "In one short sentence, confirm that you are working."
NOT_CONFIGURED_HELP = (
    "No AI provider is configured. Set LLM_PROVIDER and LLM_DEFAULT_MODEL (and GEMINI_API_KEY for "
    "gemini) in your local .env, make sure docker-compose.yml passes them to the backend, then "
    "restart it: docker compose up -d backend"
)


def _tokens(value: int | None) -> str:
    return str(value) if value is not None else "unavailable"


def _timeouts(settings: Settings) -> TimeoutPolicy:
    return TimeoutPolicy(
        connect=settings.llm_connect_timeout_seconds,
        generation=settings.llm_generation_timeout_seconds,
        stream_inactivity=settings.llm_stream_inactivity_timeout_seconds,
        overall=settings.llm_overall_timeout_seconds,
    )


async def list_models_report(settings: Settings) -> str:
    provider_name = settings.llm_provider.lower()
    if not provider_name:
        raise LLMNotConfiguredError()
    provider = get_provider(provider_name, settings)
    try:
        models = await provider.list_models()
    finally:
        await provider.aclose()

    wanted = settings.llm_default_model
    lines = [
        f"Provider: {provider_name}",
        f"Models available to the configured key: {len(models)}",
        "",
    ]
    for m in sorted(models, key=lambda x: x.provider_model_id):
        methods = ",".join(m.supported_methods) or "-"
        marker = "  <- LLM_DEFAULT_MODEL" if wanted and m.provider_model_id == wanted else ""
        lines.append(
            f"{m.provider_model_id}  |  {m.display_name or '-'}  |  methods: {methods}  |  "
            f"input limit: {m.input_token_limit or '?'}  |  "
            f"output limit: {m.output_token_limit or '?'}"
            f"{marker}"
        )
    if wanted and not any(m.provider_model_id == wanted for m in models):
        lines += ["", f"WARNING: LLM_DEFAULT_MODEL={wanted!r} is not in this list."]
    elif not wanted:
        lines += ["", "LLM_DEFAULT_MODEL is not set. Pick an id from the list above."]
    return "\n".join(lines)


async def smoke_test_report(settings: Settings, *, stream: bool = False) -> str:
    registry = build_registry(settings)
    if not registry.configured or registry.provider is None:
        raise LLMNotConfiguredError()
    model = registry.default
    provider = get_provider(registry.provider, settings)
    request = LLMRequest(
        model=model.provider_model_id,
        system_prompt="You are a concise assistant used for a connectivity test.",
        messages=[LLMMessage(Role.user, SMOKE_PROMPT)],
        max_output_tokens=min(settings.llm_max_output_tokens, 200),
        thinking_budget=settings.llm_thinking_budget,
        timeouts=_timeouts(settings),
        request_tag="smoke-test",
    )

    lines = [f"Provider: {registry.provider}", f"Model: {model.provider_model_id}"]
    started = time.monotonic()
    try:
        if model.capabilities.count_tokens:
            counted = await provider.count_tokens(request)
            lines.append(
                f"Counted input tokens: {counted if counted is not None else 'unavailable'}"
            )
        if stream and model.capabilities.streaming:
            text, first = "", None
            finish = usage = None
            async for event in provider.stream(request):
                if isinstance(event, StreamDelta):
                    first = first if first is not None else time.monotonic() - started
                    text += event.text
                elif isinstance(event, StreamEnd):
                    finish, usage = event.finish_reason, event.usage
            lines.append(
                f"Mode: streaming (first text after {first:.2f}s)" if first else "Mode: streaming"
            )
        else:
            response = await provider.generate(request)
            text, finish, usage = response.content, response.finish_reason, response.usage
            lines.append("Mode: single response")
    except LLMError as exc:
        lines.append(f"FAILED: {exc.code}")
        raise DiagnosticFailed("\n".join(lines)) from exc
    finally:
        await provider.aclose()

    elapsed = time.monotonic() - started
    if usage is None or finish is None:
        raise DiagnosticFailed("\n".join([*lines, "FAILED: no response"]))
    lines += [
        f"Reply: {text.strip()}",
        f"Finish reason: {finish.value}",
        f"Input tokens: {_tokens(usage.input_tokens)}",
        f"Output tokens: {_tokens(usage.output_tokens)}",
        f"Usage source: {usage.source.value}",
        f"Total time: {elapsed:.2f}s",
        "Result: OK",
    ]
    return "\n".join(lines)


class DiagnosticFailed(Exception):
    """Carries the partial report out to the script, which prints it and exits non-zero."""
