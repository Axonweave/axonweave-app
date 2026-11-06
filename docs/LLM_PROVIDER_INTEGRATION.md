# LLM provider integration

How providers are configured, how model selection works, and exactly how to add another provider
(including Qwen or Llama through an OpenAI-compatible adapter). Design background: `docs/AI_ARCHITECTURE.md`
sections 3 to 6 and 15. No credentials appear here; use placeholders.

## 1. Configuration (environment variables only)

Set these in your local `.env` (gitignored). `docker-compose.yml` lists each backend variable explicitly under
`environment:`, so **a new variable must also be added there** or the container never sees it.

| Variable | Meaning |
|---|---|
| `LLM_PROVIDER` | `gemini` (real), `fake` (tests and local UI work only; refused outside development/testing), or empty. Empty means the app runs and AI endpoints answer 503 `LLM_NOT_CONFIGURED`. |
| `LLM_DEFAULT_MODEL` | The provider's model id. **Never typed from memory:** list what your key can use with the script below. |
| `LLM_ALLOWED_MODELS` | Optional comma-separated extra model ids users may choose. |
| `GEMINI_API_KEY` | Backend only, held as `SecretStr`. Never sent to the frontend, stored in the database or logged. |
| `LLM_MODEL_MAX_INPUT_TOKENS`, `LLM_MODEL_MAX_OUTPUT_TOKENS` | Optional verified limits for the default model. Unknown means a conservative fallback (`LLM_FALLBACK_INPUT_TOKENS`). |
| `LLM_MAX_INPUT_CHARS` (8000), `LLM_MAX_OUTPUT_TOKENS` (2000), `LLM_HISTORY_LIMIT` (20), `LLM_THINKING_BUDGET` | Request limits. |
| `LLM_CONNECT_TIMEOUT_SECONDS` (10), `LLM_GENERATION_TIMEOUT_SECONDS` (60), `LLM_STREAM_INACTIVITY_TIMEOUT_SECONDS` (30), `LLM_OVERALL_TIMEOUT_SECONDS` (120), `LLM_MAX_RETRIES` (2) | Timeouts and retries (retries only before the first streamed token). |
| `AI_REQUESTS_PER_MINUTE_PER_USER` (10), `AI_DAILY_MESSAGE_QUOTA` (50), `AI_DAILY_TOKEN_QUOTA` (200000), `AI_MAX_ACTIVE_GENERATIONS_PER_USER` (2), `AI_STALE_GENERATION_SECONDS` (300) | Per-user controls. |
| `FAKE_LLM_CHUNK_DELAY_SECONDS` | Fake provider only; pause between chunks so tests can press Stop. |

### Steps to connect Gemini

1. Put `LLM_PROVIDER=gemini` and your key in `.env`. Leave `LLM_DEFAULT_MODEL` empty for now.
2. `docker compose up -d backend`.
3. List usable models (names only; the key is never printed):
   `docker compose exec backend python scripts/list_llm_models.py`
4. Choose one that supports content generation and set `LLM_DEFAULT_MODEL=<id>`; restart the backend.
5. `docker compose exec backend python scripts/llm_smoke_test.py --stream` sends one real request and prints the
   reply, token counts and timing. On failure it prints only an error code and the exception class.
6. Optional live tests (they cost a little): `docker compose exec backend pytest -m live tests/ai`.
   They are skipped without a key and are **not** part of the normal run. Always use `-m "not live"` for routine runs,
   because a configured key makes live tests eligible.

Prices (D-39): add a model's price to the pricing registry (`backend/app/ai/usage/pricing.py`) only after checking the
provider's current published price, with the source URL and verification date. Until then cost is unknown (`NULL`),
never 0. See `docs/USAGE_AND_COST_TRACKING.md`.

## 2. How models are selected

`backend/app/ai/model_registry.py` builds the list of enabled models from the settings above; there are no model ids
in code (D-38). The default is `LLM_DEFAULT_MODEL`; each `LLM_ALLOWED_MODELS` entry is an extra model. The client may send
`model_id` (the internal id from `GET /ai/models`); anything not in that list is rejected with 422 `LLM_INVALID_MODEL`.
The model is stored on the conversation and on each assistant message and usage record. The UI shows a model selector only
when more than one model is enabled. Capabilities (streaming, usage reporting, system prompt, token counting) come from
the provider class and drive explicit degradation rather than crashes.

## 3. How a provider is structured

A provider is one class implementing `LLMProvider` (`backend/app/ai/providers/base.py`):

- `create(settings)` builds it, or raises `LLMNotConfiguredError` without credentials.
- `generate(request)` returns an `LLMResponse`; `stream(request)` yields `StreamDelta` events then exactly one `StreamEnd`
  with usage. If the consumer stops iterating, the adapter must cancel the upstream call.
- `count_tokens` (optional, returns `None` if unsupported), `list_models` (used by the discovery script), `aclose`.
- It raises **only** `LLMError` subclasses (`app/ai/errors.py`), never retries (the orchestrator does), enforces the
  timeouts carried by the request, never returns vendor objects, and never puts vendor error text in an exception message.
- A test (`test_no_provider_sdk_imported_outside_providers_package`) fails if a vendor SDK is imported outside
  `backend/app/ai/providers/`.

Adding any provider is: one adapter file, one line in `_ADAPTERS` in `providers/registry.py`, and configuration. Nothing in
routes, orchestration, the database schema or the frontend changes.

## 4. Adding Qwen or Llama through an OpenAI-compatible adapter

Qwen and Llama are usually served by software that exposes an OpenAI-compatible HTTP API: Ollama
(`http://<host>:11434/v1`), vLLM (`vllm serve`, default port 8000, path `/v1`), llama.cpp's server (port 8080, `/v1`), or a hosted
service. One generic adapter covers all of them, using `httpx` (already a dependency), so no new SDK is needed.

> Status: **this is a guide, not shipped code.** The skeleton below has not been run against any server. Treat it as a starting
> point and test it. Verify the request and response fields against the documentation of the server you use.

### Steps

1. **Run a server** and note its base URL and the exact model name it serves (for example `ollama list`, or `GET <base>/models`).
   From inside the backend container, a server on your host is reached at `http://host.docker.internal:<port>/v1`, not `localhost`.
2. **Add the adapter** `backend/app/ai/providers/openai_compat_provider.py` (skeleton below).
3. **Register it:** add `"openai_compat": "app.ai.providers.openai_compat_provider:OpenAICompatProvider"` to `_ADAPTERS` in
   `backend/app/ai/providers/registry.py`.
4. **Add the settings to the environment, in three places:**
   - `.env.example`: `OPENAI_COMPAT_BASE_URL=` and `OPENAI_COMPAT_API_KEY=` (placeholders only).
   - `docker-compose.yml` under `backend.environment`: pass both through (`${OPENAI_COMPAT_BASE_URL:-}`).
   - The adapter reads them with its own small settings class, so the core `Settings` is untouched.
5. **Configure the model:** `LLM_PROVIDER=openai_compat`, `LLM_DEFAULT_MODEL=<name as served>`, optionally `LLM_ALLOWED_MODELS`.
   Restart the backend. The model appears in `GET /ai/models` and the AI Tutor with no frontend change.
6. **Prices:** a local model has no price, so cost stays unknown, which the UI already shows. A hosted service needs a verified
   price entry as in section 1.
7. **Tests** (required before merging): adapter unit tests against a mocked HTTP transport (`httpx.MockTransport`) for each error
   mapping, normal and streaming responses, a stream that ends without usage, and cancellation; plus the existing import-boundary
   test. Add a smoke script run (`scripts/llm_smoke_test.py --stream`) against the real server and record the result.
8. **Evaluate** with `docs/ai_eval/questions.yaml` on the same caps as the current provider before choosing it
   (`docs/AI_EVALUATION.md`).
9. Update `docs/DECISIONS.md` and the privacy notice if conversations will go to a different party (for a self-hosted model they stay on
   your infrastructure; the notice text is driven by `provider_display_name`, which the adapter sets).

### Adapter skeleton (illustrative)

```python
"""OpenAI-compatible adapter (Qwen, Llama and others served over /v1/chat/completions)."""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, Self

import httpx
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.ai.errors import (LLMAuthFailedError, LLMBadResponseError, LLMInvalidModelError,
                           LLMNotConfiguredError, LLMRateLimitedError, LLMTimeoutError,
                           LLMUnavailableError)
from app.ai.providers.base import LLMProvider
from app.ai.types import (Capabilities, FinishReason, LLMRequest, LLMResponse, StreamDelta,
                          StreamEnd, StreamEvent, Usage, UsageSource)
from app.core.config import Settings


class _Cfg(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OPENAI_COMPAT_", extra="ignore")
    base_url: str = ""
    api_key: SecretStr | None = None


def _body(req: LLMRequest, stream: bool) -> dict[str, Any]:
    msgs = ([{"role": "system", "content": req.system_prompt}] if req.system_prompt else [])
    msgs += [{"role": m.role.value, "content": m.content} for m in req.messages]
    body: dict[str, Any] = {"model": req.model, "messages": msgs,
                            "max_tokens": req.max_output_tokens, "stream": stream}
    if stream:
        body["stream_options"] = {"include_usage": True}  # not every server honours this
    return body


def _raise_for(status: int) -> None:
    if status in (401, 403):
        raise LLMAuthFailedError()
    if status == 404:
        raise LLMInvalidModelError()
    if status == 429:
        raise LLMRateLimitedError()
    if status >= 500:
        raise LLMUnavailableError()
    raise LLMBadResponseError()


class OpenAICompatProvider(LLMProvider):
    name = "openai_compat"
    display_name = "OpenAI-compatible server"   # shown in the privacy notice; set per deployment
    capabilities = Capabilities(streaming=True, structured_output=False, usage_reporting=False,
                                system_prompt=True, count_tokens=False, thinking_budget=False)

    def __init__(self, cfg: _Cfg) -> None:
        self._cfg = cfg
        self._client = httpx.AsyncClient(base_url=cfg.base_url.rstrip("/"))

    @classmethod
    def create(cls, settings: Settings) -> Self:
        cfg = _Cfg()
        if not cfg.base_url:
            raise LLMNotConfiguredError()
        return cls(cfg)

    def _headers(self) -> dict[str, str]:
        key = self._cfg.api_key.get_secret_value() if self._cfg.api_key else ""
        return {"Authorization": f"Bearer {key}"} if key else {}

    async def generate(self, request: LLMRequest) -> LLMResponse:
        try:
            r = await self._client.post("/chat/completions", json=_body(request, False),
                                        headers=self._headers(),
                                        timeout=request.timeouts.generation)
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError() from exc
        except httpx.HTTPError as exc:
            raise LLMUnavailableError() from exc
        if r.status_code >= 400:
            _raise_for(r.status_code)
        data = r.json()
        choice = data["choices"][0]
        u = data.get("usage") or {}
        usage = (Usage(u.get("prompt_tokens"), u.get("completion_tokens"),
                       source=UsageSource.provider_reported) if u else Usage())
        text = choice["message"]["content"] or ""
        if not text:
            raise LLMBadResponseError()
        return LLMResponse(text, request.model, FinishReason.stop, usage)

    async def stream(self, request: LLMRequest) -> AsyncIterator[StreamEvent]:
        # POST with stream=True, iterate `aiter_lines()`, skip blanks, stop at "data: [DONE]",
        # json.loads each "data: {...}" line, yield StreamDelta(choice["delta"].get("content", "")),
        # remember `finish_reason` and the final `usage` chunk, then yield one StreamEnd.
        # Map failures exactly as in generate(); closing the async generator must close the response.
        raise NotImplementedError

    async def aclose(self) -> None:
        await self._client.aclose()
```

The `stream` body is left as a comment on purpose: it needs testing against the real server's chunk format (some send usage in the last
chunk, some not at all; when absent, report `Usage()` so the usage record is `unavailable`, never a guess).

### What does not change

Routes and schemas, the orchestration service, the context manager (it falls back to a character estimate when `count_tokens`
is off), prompts, the database (provider and model are rows, capabilities are JSON), quotas, the SSE protocol, and the frontend.
