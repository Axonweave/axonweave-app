# AI architecture (Phase 2, spec Step 2)

Status: written as the Step 2 design and kept up to date; the sections below describe what was built unless marked otherwise (see "As built" at the end for the changes made while implementing). Decisions referenced as D-nn are in `docs/DECISIONS.md` (D-37 onward).
Context: `docs/AI_INTEGRATION_PLAN.md` (how Phase 1 works and where this plugs in).

## 1. Principles

1. **Provider independent.** Gemini is the first provider. Nothing outside `backend/app/ai/providers/` imports a provider SDK. A test enforces this.
2. **Adding a provider is one new adapter file, one registry entry and model configuration.** No change to routes, orchestration, database schema or frontend (section 15 walks through it for Qwen and Llama).
3. **Capabilities, not assumptions.** Each model declares what it supports. A missing capability degrades explicitly or returns a clean error; it never crashes.
4. **The backend owns the conversation.** Providers are stateless. Every request carries the context the backend chose.
5. **Output is untrusted.** Permissions are enforced in code, never by prompts.
6. **Unknown is not zero.** Missing token counts and unknown prices are `NULL`, never `0`.
7. **Runs without a provider.** AI endpoints answer 503 `LLM_NOT_CONFIGURED`; everything else works (D-58).

## 2. Component map

```
route (modules/ai/*)           HTTP, auth (ActiveUser), schemas only
  -> service (modules/ai/*)    ownership, quotas, transactions, persistence
     -> orchestration.AiService   builds the request, runs the provider, handles retries/errors
          -> ContextManager       what history goes in
          -> PromptRegistry       which system prompt (key + version)
          -> ModelRegistry        which model, which capabilities
          -> ProviderRegistry     name -> adapter instance
               -> providers/<x>   the ONLY code that knows a vendor SDK
     -> repositories             SQL only
```

`AiService` knows nothing about HTTP, SSE framing or SQL. It receives plain inputs and yields typed events. The module services persist and the routes frame.

## 3. Provider interface and typed models

All types are Pydantic models or frozen dataclasses in `app/ai/types.py`. Provider SDK objects never leave an adapter.

```python
class Role(StrEnum): system; user; assistant; tool          # tool reserved, unused in Phase 2

class LLMMessage:   role: Role; content: str

class LLMRequest:
    model: str                      # provider model id, from ModelConfig
    system_prompt: str | None       # kept separate from messages, always
    messages: list[LLMMessage]      # user/assistant turns only, oldest first
    temperature: float | None
    max_output_tokens: int
    timeouts: TimeoutPolicy         # connect, generation, stream_inactivity, overall
    thinking_budget: int | None     # honoured only if the model declares it
    request_tag: str                # opaque id for logs; never sent to the provider

class Usage:
    input_tokens: int | None
    output_tokens: int | None       # includes reasoning/thought tokens when the model reports them
    reasoning_tokens: int | None    # the reasoning part of output_tokens, when reported
    source: UsageSource             # provider_reported | estimated | unavailable

class LLMResponse:
    content: str
    model: str
    finish_reason: FinishReason     # stop | length | content_filter | error | other
    usage: Usage
    provider_request_id: str | None

# streaming
class StreamDelta:  text: str
class StreamEnd:    finish_reason; usage: Usage; provider_request_id
StreamEvent = StreamDelta | StreamEnd
```

```python
class LLMProvider(ABC):
    name: str

    async def generate(self, request: LLMRequest) -> LLMResponse: ...
    def stream(self, request: LLMRequest) -> AsyncIterator[StreamEvent]: ...
    async def count_tokens(self, request: LLMRequest) -> int | None: ...   # None = unsupported
    async def generate_structured(self, request, schema) -> StructuredResponse: ...  # capability-gated
    async def aclose(self) -> None: ...
```

Contract for adapters:

- Convert `LLMRequest` to the vendor format and the vendor response to `LLMResponse`. Normalise roles and finish reasons.
- Raise only `LLMError` subclasses (section 5). Vendor exceptions are caught and mapped inside the adapter; the raw message is logged without content and never returned.
- `stream()` yields zero or more `StreamDelta` then exactly one `StreamEnd`. If the consumer cancels, the adapter cancels the upstream call (close the HTTP stream) and returns.
- Enforce the timeouts in `TimeoutPolicy` (connect, generation, inactivity between chunks, overall).
- Report usage honestly: `provider_reported` only when the vendor sent numbers; otherwise `unavailable` (the orchestrator may then add an estimate and mark it `estimated`).
- No retries inside the adapter. Retrying is the orchestrator's job (D-50) so the policy is the same for every provider.

## 4. Capabilities and explicit degradation

```python
class Capabilities:
    streaming: bool
    structured_output: bool
    usage_reporting: bool
    system_prompt: bool
    tool_calling: bool          # reserved, always false in Phase 2
    count_tokens: bool
    thinking_budget: bool
```

| Missing capability | What happens |
|---|---|
| `streaming` | The orchestrator calls `generate()` and emits one `message.delta` with the whole text, then `message.completed`. The UI behaves the same. |
| `system_prompt` | The adapter folds the system prompt into the first user turn inside clearly delimited instructions. The `ModelConfig` flag documents this; the conversation is unchanged in the database. |
| `usage_reporting` | Tokens are estimated and recorded with `usage_source = estimated`. If even that is impossible, `unavailable` with `NULL` counts. |
| `count_tokens` | The context manager uses the conservative character estimate and flags it as an estimate (D-47). |
| `structured_output` | `generate_structured` raises `LLMCapabilityError`; the caller gets a 422 `LLM_INVALID_MODEL` style error, not a crash. Phase 2 has no user-facing caller for it. |
| `thinking_budget` | The setting is ignored for that model. |
| `tool_calling` | Not implemented in Phase 2. |

`GET /ai/models` and `GET /ai/capabilities` expose only these flags and safe metadata (display name, default flag), never keys, base URLs or provider internals.

## 5. Error taxonomy

All provider failures become `LLMError(code, user_message, retryable, http_status)`. The user-facing message is generic and fixed per code; the provider's own text is never returned (D-49, spec 14.7).

| Code | HTTP | Retryable | Meaning / user message |
|---|---|---|---|
| `LLM_NOT_CONFIGURED` | 503 | no | No provider or model configured (D-58). |
| `LLM_AUTH_FAILED` | 502 | no | Bad or missing provider credentials. User sees "The AI service is unavailable." Logged as a security-relevant event. |
| `LLM_RATE_LIMITED` | 429 | yes (before first token) | The provider is throttling us. `Retry-After` when known. |
| `LLM_TIMEOUT` | 504 | yes (before first token) | Connect, generation, inactivity or overall timeout. |
| `LLM_UNAVAILABLE` | 503 | yes (before first token) | Network failure, provider 5xx. |
| `LLM_CONTEXT_TOO_LONG` | 422 | no | The latest message alone exceeds the budget (D-47). |
| `LLM_CONTENT_BLOCKED` | 422 | no | The provider blocked the prompt or response (safety). |
| `LLM_INVALID_MODEL` | 422 | no | Model id not in the allowed registry, or the provider rejected it. |
| `LLM_BAD_RESPONSE` | 502 | no | Empty, malformed or unexpected provider response. |
| `AI_QUOTA_EXCEEDED` | 429 | no | Per-user daily message or token quota, or request rate limit. Always has `Retry-After`. |
| `AI_GENERATION_IN_PROGRESS` | 409 | no | Another generation is active in this conversation, or the per-user cap is reached. |
| `CONVERSATION_NOT_FOUND` | 404 | no | Not found **or not owned** (D-56). |

Delivery:

- **Before any streamed byte:** a normal error envelope with the HTTP status above.
- **After streaming started:** the HTTP status is already 200, so the error is a `message.failed` event with `{code, message}`; the message row becomes `failed` with `error_code`.
- Retry policy (D-50): only `retryable` errors, only before the first token was received, at most `LLM_MAX_RETRIES` (default 2), exponential backoff with jitter, honouring `Retry-After`. Never retry after content started.

## 6. Provider registry and model registry

### 6.1 Provider registry (`ai/providers/registry.py`)

The only file that maps a provider name to an adapter:

```python
PROVIDER_FACTORIES: dict[str, ProviderFactory] = {
    "gemini": GeminiProvider.create,
    "fake":   FakeProvider.create,
}
```

`get_provider(name)` builds the adapter once (lazy, cached), passing it only what it declares. Each adapter declares its own small settings class, so core `Settings` does not change when a provider is added (core `Settings` ignores unknown variables):

```python
class GeminiSettings(BaseSettings):
    gemini_api_key: SecretStr | None = None
```

### 6.2 Model registry (`ai/model_registry.py`, no SDK imports)

```python
class ModelConfig:
    internal_id: str          # stable id used by the API and stored on messages ("default", "m-<slug>")
    provider: str             # key in PROVIDER_FACTORIES
    provider_model_id: str    # from env, verified; never typed in code from memory (D-38)
    display_name: str
    enabled: bool
    capabilities: Capabilities
    max_input_tokens: int | None      # verified limit, None = unknown
    max_output_tokens: int | None
    default_temperature: float | None
    config_version: str
```

Built at startup from settings: `LLM_DEFAULT_MODEL` becomes internal id `default`; each entry in `LLM_ALLOWED_MODELS` becomes an extra model. Capabilities come from a per-provider capability profile declared in the adapter file and may be refined per model. The list is **upserted into `llm_providers` / `llm_models`** at startup so usage rows can reference them (D-37). No secrets are stored in those rows.

`ModelRegistry.resolve(internal_id | None)` returns the default for `None` and raises `LLM_INVALID_MODEL` for unknown or disabled ids. There is no automatic fallback between providers in Phase 2 (spec 6.4): failures are reported clearly.

### 6.3 Model discovery script (D-38)

`docker compose exec backend python scripts/list_llm_models.py` calls the configured provider's model-listing API and prints, for each model, the provider model id, display name, supported generation methods and the input/output token limits if the API returns them. It never prints the key, request headers or the full environment. The chosen id and the date it was verified are recorded in `docs/LLM_PROVIDER_INTEGRATION.md` (M1).

## 7. Orchestration

### 7.1 Send a message (non-streaming and streaming share steps 1 to 6)

1. **Auth and ownership:** load the conversation by `(id, user_id)`; absent means 404 `CONVERSATION_NOT_FOUND`.
2. **Validate:** resolve model, check `len(content) <= LLM_MAX_INPUT_CHARS`, provider configured.
3. **Quotas (D-43):** request-rate limiter (existing `RateLimiter`, key `ai:user:<id>`), daily message and token quotas from `ai_usage_records`/`messages`, per-user active-generation cap.
4. **Transaction A (short):** lock the conversation row (`SELECT ... FOR UPDATE`); insert the user message (`sequence_number = max + 1`) and a `pending` assistant message (`sequence_number + 1`), setting `prompt_key` and `prompt_version`. The partial unique index rejects a second active assistant message in the same conversation, which becomes 409 `AI_GENERATION_IN_PROGRESS`. The per-user cap is enforced here too, by locking the user's row first so two concurrent requests cannot both pass (D-43). Commit.
5. **Context (D-47):** `ContextManager.build()` returns the system prompt and message list within budget, or raises `LLM_CONTEXT_TOO_LONG`.
6. **Call the provider** through `AiService` with the retry policy.
7. **Non-streaming:** on success, transaction B: store content, status `completed`, usage, finish reason, `completed_at`; insert the `ai_usage_records` row; update `conversations.last_message_at`. On error: status `failed` with `error_code`; usage row with `request_status = failed`.
8. **Streaming:** see section 12.

Title (D-55): after the first user message, if the title is still the default, set it from the first ~60 characters with whitespace collapsed. Titles never require an LLM call.

### 7.2 Regenerate (D-42)

`POST .../messages/{message_id}/regenerate` targets an assistant message. In one locked transaction: reject if a generation is active; mark the target `superseded_at = now()`; insert a new `pending` assistant message with `regenerates_message_id = target`, next `sequence_number`. The context manager ignores superseded rows and builds history up to the user message that preceded the target. The old row stays for history. Repeated clicks hit the partial unique index and return 409.

### 7.3 Cancel (D-45)

`POST .../messages/{message_id}/cancel` checks ownership, then asks the in-process `GenerationRegistry` (message id to the running task and a cancel event) to stop. The streaming task cancels the upstream call, flushes the partial content, sets status `cancelled`, records any usage the provider reported (otherwise `unavailable`). If the registry has no entry (finished, other process, crash), the endpoint returns the message's current state; if the row is still `pending/streaming` and stale, recovery handles it. Single-instance limit documented, same as D-18.

### 7.4 Recovery (D-46)

At startup (lifespan) and then periodically (an `asyncio` task every 60 seconds) mark assistant messages that are `pending` or `streaming` and older than `AI_STALE_GENERATION_SECONDS` as `failed` with `error_code = LLM_UNAVAILABLE`. This releases the partial unique index after a crash and keeps stuck rows from looking successful.

## 8. Database design

All primary keys UUID, all timestamps UTC with time zone, every constraint declared on the SQLAlchemy model (D-61) and created by Alembic. New tables are granted to `axonweave_app` (verified in M1, D-33).

### 8.1 Tables

**`llm_providers`**: `id`, `provider_name` UNIQUE, `display_name`, `is_enabled`, timestamps. No secrets.

**`llm_models`**: `id`, `provider_id` FK `llm_providers` RESTRICT, `internal_id` UNIQUE, `provider_model_id`, `display_name`, `is_enabled`, `capabilities` JSONB, `max_input_tokens`, `max_output_tokens`, `config_version`, timestamps. UNIQUE (`provider_id`, `provider_model_id`).

**`llm_model_prices`** (D-39): `id`, `model_id` FK `llm_models` RESTRICT, `input_price_per_1m` NUMERIC, `output_price_per_1m` NUMERIC, `currency`, `effective_from`, `pricing_version` UNIQUE, `source_note`. Rows only after verification against the provider's current pricing page.

**`prompt_templates`** (D-41): `id`, `prompt_key`, `version`, `content`, `content_sha256`, `is_active`, timestamps. UNIQUE (`prompt_key`, `version`); partial unique index on (`prompt_key`) WHERE `is_active`. Synced from source files at startup; an existing (`key`, `version`) whose hash differs is an error: bump the version instead.

**`conversations`**: `id`, `user_id` FK `users` ON DELETE CASCADE, `title`, `status` ('active','archived'), `model_id` VARCHAR (internal id), `created_at`, `updated_at`, `last_message_at`. UNIQUE (`id`, `user_id`) (target of composite FKs). Index (`user_id`, `last_message_at` DESC). CHECK on `status`.

**`messages`**: `id`, `conversation_id`, `user_id` (denormalised owner), `role`, `content`, `status`, `sequence_number`, `model_id` VARCHAR, `prompt_key`, `prompt_version`, `input_tokens`, `output_tokens`, `reasoning_tokens`, `usage_source`, `finish_reason`, `error_code`, `regenerates_message_id`, `superseded_at`, `created_at`, `updated_at`, `completed_at`.
- FK (`conversation_id`, `user_id`) -> `conversations`(`id`, `user_id`) ON DELETE CASCADE. A message can never point at a conversation with a different owner (D-56, spec 13.3).
- UNIQUE (`conversation_id`, `sequence_number`) (D-42).
- UNIQUE (`id`, `user_id`) (target for feedback and usage FKs).
- Partial UNIQUE index on (`conversation_id`) WHERE `role = 'assistant' AND status IN ('pending','streaming')` (D-43).
- FK `regenerates_message_id` -> `messages`(`id`) ON DELETE SET NULL.
- CHECKs: `role` in (system, user, assistant, tool), `status` in (pending, streaming, completed, failed, cancelled), `usage_source` in (provider_reported, estimated, unavailable), token counts >= 0.
- The system prompt is **not** stored as a row (D-41). `role = 'system'` and `'tool'` are allowed by the CHECK for future use and never written in Phase 2.

**`message_feedback`**: `id`, `message_id`, `user_id`, `rating` ('positive','negative'), `feedback_text`, `created_at`. FK (`message_id`, `user_id`) -> `messages`(`id`, `user_id`) ON DELETE CASCADE, so feedback can only be given by the message's owner. UNIQUE (`message_id`, `user_id`).

**`ai_usage_records`** (D-40, D-53): `id`, `user_id` FK `users` ON DELETE CASCADE, `conversation_id` NULL, `message_id` NULL, `provider_id` FK, `model_id` FK `llm_models` RESTRICT, `input_tokens`, `output_tokens`, `reasoning_tokens` (all NULL-able), `usage_source`, `estimated_cost` NUMERIC NULL, `currency` NULL, `pricing_version` NULL (snapshot, so history is never recalculated), `request_status`, `error_code`, `duration_ms`, `provider_request_id`, `created_at`.
- FK (`conversation_id`, `user_id`) -> `conversations`(`id`, `user_id`) **ON DELETE SET NULL (`conversation_id`)** and FK (`message_id`, `user_id`) -> `messages`(`id`, `user_id`) **ON DELETE SET NULL (`message_id`)**: deleting a conversation keeps usage history without content and without nulling `user_id`. The column-list form needs PostgreSQL 15+ (we run 16); M1 verifies SQLAlchemy/Alembic emit it, with a service-level fallback if not.
- Indexes: (`user_id`, `created_at`), (`model_id`, `created_at`).
- Deleting the account removes these rows through `user_id` ON DELETE CASCADE.

**`user_preferences.ai_notice_acknowledged_at`** (D-54): nullable timestamp, in a separate small migration.

### 8.2 Deletion and export (D-53)

- Delete conversation: its messages and feedback are hard-deleted by cascade; usage rows stay with `conversation_id`/`message_id` NULL.
- Delete account: `users` cascade removes conversations, messages, feedback and usage.
- `GET /users/me/export` gains `ai_conversations` (with messages and feedback) and `ai_usage`. Message content is included because it is the user's own data; it is still never logged.

### 8.3 Ordering

`sequence_number` is assigned inside the transaction that holds the conversation row lock (`SELECT ... FOR UPDATE`), as `COALESCE(MAX(sequence_number), 0) + 1`. The unique constraint is the backstop.

## 9. Context manager (D-47, D-48)

Input: conversation id, owner, the new user message, model. Output: `system_prompt`, `messages`, `estimated: bool`, `dropped_messages: int`.

1. Budget = model `max_input_tokens` minus reserved output (`LLM_MAX_OUTPUT_TOKENS`). Unknown limit falls back to a conservative configured default.
2. Always include the system prompt and the latest user message. If those alone exceed the budget: 422 `LLM_CONTEXT_TOO_LONG`.
3. Take previous messages for this conversation only, excluding `superseded_at IS NOT NULL`, `failed`, `cancelled` and the pending assistant row, limited to `LLM_HISTORY_LIMIT` messages.
4. Walk **complete turns** (user plus its assistant answer) from newest to oldest, adding while the budget holds. A turn is dropped whole, never cut in the middle.
5. Token counting: provider `count_tokens` when the model declares it; otherwise a character-based estimate (characters / 3, rounded up, deliberately conservative) and `estimated = True`. The result is logged as a count, never as text.

Context providers: the manager takes a list of `ContextSource` objects (Phase 2 has only `ConversationHistory`). Workspace, subject, chapter or document sources can be added later without changing callers. Nothing else is sent: no profile data, no other conversations, no secrets (spec 10.4, 15.4).

## 10. Prompt registry (D-41)

- Prompts are versioned source files (`ai/prompts/academic_tutor.py`: `PROMPT_KEY = "academic_tutor"`, `VERSION = "1"`, `CONTENT = ...`).
- At startup the registry syncs them into `prompt_templates` (insert new versions, activate the configured one, error on hash mismatch for an existing version).
- Each assistant message stores `prompt_key` and `prompt_version`. The prompt text itself is not duplicated per message and not stored as a message row.
- The system prompt goes in the provider's system field, never concatenated into user text. User text cannot change it. Model output that quotes it is not a security event, but the prompt contains no secrets.
- Changing a prompt means a new version. Old versions stay in the table.

## 11. Usage, cost and quotas (D-39, D-40, D-43)

- Every provider call (success, failure, cancellation) writes one `ai_usage_records` row in the same transaction that finalises the message.
- Token fields come from the provider when reported (`provider_reported`). Reasoning/thought tokens, when reported, are included in `output_tokens` and also stored in `reasoning_tokens` for transparency; the docs state this. If streaming gives usage only at the end, that final figure is used. If the stream is cancelled before usage arrives: `unavailable` with NULL counts, not a guess presented as fact.
- Cost = input/1M x input price + output/1M x output price, computed only when both token counts and a price effective at the request time exist. Otherwise `estimated_cost` is NULL. The `pricing_version` used is stored on the row.
- Quotas (all configurable, conservative): requests per minute per user (rate limiter), daily message count and daily token total per user (from the database, so they survive restarts and work across workers), maximum active generations per user (database lock plus count). Exceeding any returns 429 `AI_QUOTA_EXCEEDED` (or 409 `AI_GENERATION_IN_PROGRESS` for the concurrency cap) with `Retry-After`. The frontend cannot bypass these.
- `GET /ai/usage`, `/ai/usage/summary`, `/ai/usage/by-model` return only the caller's rows.

## 12. Streaming protocol (D-44)

Endpoint: `POST /api/v1/ai/conversations/{id}/messages` with `{"content", "model_id", "stream": true}`. Non-streaming (`stream: false`) returns the JSON envelope of spec 14.6.

Transport: `Content-Type: text/event-stream; charset=utf-8`, `Cache-Control: no-store`, `X-Accel-Buffering: no`, `Connection: keep-alive`. The client uses `fetch` with `credentials: "include"` and the `X-CSRF-Token` header and reads the body stream (`EventSource` cannot POST or set headers). Each event has `event:` and a single-line JSON `data:` (JSON escaping prevents model text from breaking the framing). A comment line `: ping` is sent every 15 seconds as a heartbeat.

| Event | Data |
|---|---|
| `message.started` | `{"message_id", "user_message_id", "conversation_id", "model_id"}` |
| `message.delta` | `{"delta": "text"}` |
| `usage.updated` | `{"input_tokens", "output_tokens", "usage_source"}` (nullable fields), sent once at the end |
| `message.completed` | `{"message_id", "finish_reason"}` |
| `message.failed` | `{"message_id", "code", "message"}` (generic message, D-49) |
| `message.cancelled` | `{"message_id"}` |

Server behaviour:

1. Steps 1 to 5 of 7.1 happen before the first event, so quota, ownership and context errors are normal HTTP errors.
2. Send `message.started`; the assistant row moves to `streaming`.
3. Forward deltas. Accumulate content and flush it to the row every ~2 seconds or ~1 KB, so a crash or disconnect keeps what was produced.
4. On provider end: write final content, `completed`, usage, finish reason (`length` is a completed message with `finish_reason = length`), usage record, `last_message_at`; send `usage.updated` then `message.completed`.
5. On a provider error: `failed` with `error_code`, send `message.failed`, usage row with failed status.
6. **Client disconnect** or the cancel endpoint: cancel the upstream call, flush partial content, set `cancelled`, record usage if reported, send `message.cancelled` if the socket is still open. Disconnect handling runs in a shielded cleanup so the database update always happens.
7. Retries only happen before the first delta (D-50).
8. Frontend: appends deltas, shows a Stop button, on connection loss shows an error with Retry (which regenerates, creating a new attempt), and refetches the conversation from the server as the source of truth.

Known risk: `BaseHTTPMiddleware` behaviour with streaming and disconnects (integration plan 2.4); the first M3 task proves the full stack, with conversion to pure ASGI as the fallback.

## 13. Gemini adapter notes (D-57)

Official `google-genai` SDK, pinned; imported only in `gemini_provider.py`. Specifics to verify against the pinned version during M1 (the SDK surface and model names change; none of this is copied from memory into code):

- System prompt goes in the SDK's system-instruction field.
- Our `assistant` role maps to Gemini's `model` role.
- Blocked prompt or response and safety finish reasons map to `LLM_CONTENT_BLOCKED`; the max-tokens finish reason is a normal completion with `finish_reason = length`.
- Usage is read from the response's usage metadata (prompt tokens, candidate tokens, and thought tokens if present). Thought tokens are counted in output usage (D-40).
- Thinking budget is limited or disabled where the model supports it, via `LLM_THINKING_BUDGET`; ignored where it does not.
- SDK errors (auth, quota/rate limit, server, timeout, bad request) map to the taxonomy in section 5; messages are never passed on.
- Token counting uses the SDK's count-tokens call if the model declares `count_tokens`.
- Streaming uses the SDK's async streaming call and the adapter cancels it when the consumer stops.

## 14. FakeProvider (tests and local UI development only)

- Deterministic and scriptable: echoes a canned response, can simulate chunked streaming with delays, rate limits, timeouts, content blocking, malformed responses, missing usage and stream interruption. Used by all automated tests and by Playwright.
- **Refuses to start when `APP_ENV=production`**, and in any environment other than `development` or `testing`. `LLM_PROVIDER=fake` must be set explicitly; it is never a fallback. `Settings` also rejects it in production (defence in depth).
- When active, `GET /ai/capabilities` reports `provider_kind: "test"`, and the AI Tutor shows a permanent "Test provider, not a real AI" badge, so it can never pass for real output (spec 26).
- Its pricing and token counts are marked `estimated`, and it records usage under a `fake` provider row so test data is separable.

## 15. How to add Qwen or Llama later

Qwen and Llama (served locally by Ollama, vLLM or llama.cpp, or by a hosted service) normally expose an **OpenAI-compatible HTTP API**. One generic adapter covers all of them.

1. **One new adapter file:** `backend/app/ai/providers/openai_compat_provider.py`.
   - Implements `LLMProvider` (`generate`, `stream`, `count_tokens` returning `None`, `generate_structured` raising `LLMCapabilityError`).
   - Uses `httpx` (already a dependency) against `POST {base_url}/chat/completions`, with `stream: true` for SSE, so no new SDK is needed. (If an SDK is preferred, it is imported in this file only.)
   - Declares its own settings class: `OpenAICompatSettings(base_url, api_key: SecretStr | None)` read from `OPENAI_COMPAT_BASE_URL` / `OPENAI_COMPAT_API_KEY`. Core `Settings` is untouched.
   - Maps HTTP status and error bodies to the taxonomy: 401/403 to `LLM_AUTH_FAILED`, 404/model-not-found to `LLM_INVALID_MODEL`, 429 to `LLM_RATE_LIMITED`, timeouts to `LLM_TIMEOUT`, 5xx and connection errors to `LLM_UNAVAILABLE`, finish reason `content_filter` to `LLM_CONTENT_BLOCKED`.
   - Reads `usage` from the response when present (many local servers include it, some omit it in streams); otherwise reports `unavailable`.
   - Declares a capability profile (streaming true, system prompt true, usage reporting "maybe", count tokens false, structured output false).
2. **One registry entry:** in `providers/registry.py`, `"openai_compat": OpenAICompatProvider.create`.
3. **Model configuration:** set `LLM_PROVIDER=openai_compat` and `LLM_DEFAULT_MODEL=<model name as served>` (and optional `LLM_ALLOWED_MODELS`), with the base URL in the environment. The model is upserted into `llm_models` at startup.

What does **not** change: routes and schemas (`/ai/models` already returns whatever the registry holds), the orchestration service, context manager (character estimate because `count_tokens` is false), prompts, the database schema (provider and model are rows, capabilities are JSONB), quota logic, the SSE protocol, or any frontend code (the model selector, badges and degraded behaviour are driven by the capability flags). Cost is `NULL` for a free local model (no price row), which the usage UI already shows as "not available".

Checklist for the PR that adds it: adapter file, one registry line, adapter unit tests against a mocked HTTP server for every error code and the streaming path, an update to `docs/LLM_PROVIDER_INTEGRATION.md`, and the import-boundary test still passing.

## 16. Logging and privacy (D-51)

- Logged: user id, conversation id, message id, model id, provider, token counts, duration, error code, provider request id, retry count, correlation id.
- Never logged: message content, prompts, system prompt text, raw provider responses or error bodies, API keys, headers. Provider error bodies are reduced to a code before logging.
- Security events (`security` logger style): quota exceeded, provider auth failure, content blocked, cross-user access attempt (a 404 is returned and an event is logged without the target's details).
- Stored conversations are private user data: no cross-user queries exist, every repository method takes `user_id`, and deletion removes content (D-53).

## 17. Test strategy (summary)

- Provider-independent suite runs on `FakeProvider`; no network, no cost.
- Per-adapter unit tests with a mocked transport cover every taxonomy code, missing usage and stream interruption.
- Import-boundary test: no provider SDK imported outside `app/ai/providers/`.
- Schema tests: constraints exist on the model, migrations match metadata, app-role grants hold, partial unique index rejects a second active generation, composite FKs reject cross-owner rows, SET NULL keeps usage.
- Cross-user tests for every endpoint (404, nothing changed), unauthenticated sweep (401), oversized input (422), quota and concurrency (429, 409).
- Streaming tests through the real middleware stack: ordering, heartbeat, cancel, disconnect, partial flush, failure after start.
- Optional live-provider tests, marked and skipped without a key.
- Playwright on `FakeProvider`: start a chat, stream, stop, regenerate, rename, delete, switch conversations, second user isolation, mobile.

## 18. As built: differences and additions (Phase 2 close-out)

The design above was implemented as written, with these additions and notes:

- **Frontend (M4):** `frontend/src/features/ai-tutor/` holds the UI. The shell lives in the `(app)/ai-tutor` layout so a streaming chat survives the URL change when a
  conversation is created. The SSE client is a fetch-based reader with an incremental parser. After every stream the client re-reads the conversation from the
  server, which is the source of truth. Markdown is rendered by `react-markdown` + `remark-gfm` + `rehype-sanitize` with no raw HTML and safe links only (D-52).
- **Status endpoint:** `GET /ai/status` works with no provider configured and reports `configured`, `provider_display_name`, `is_test_provider` and `max_input_chars`, so the UI can show the
  "not configured" state, the privacy notice text and the input limit without calling a provider (D-54, D-58).
- **Privacy notice:** `POST /users/me/ai-notice/acknowledge` stores `user_preferences.ai_notice_acknowledged_at` (idempotent).
- **Fake provider delay:** `FAKE_LLM_CHUNK_DELAY_SECONDS` (0 to 2, fake provider only) lets browser tests press Stop mid-stream.
- **Evaluation:** `backend/scripts/run_ai_eval.py` and `docs/ai_eval/questions.yaml` (see `docs/AI_EVALUATION.md`). The runner calls the provider directly with the production
  prompt, one attempt per request, and hard caps on requests and tokens.
- **Single-instance limits (D-45):** the cancel registry and the per-minute rate limiter are in-process. Daily quotas, the one-active-generation rule and stale-generation recovery
  are database-backed and are not affected.
- **Pricing:** the price catalogue is empty, so cost is unknown for every real request until a price is verified (D-39).
- **Not built (by design, spec section 24):** document parsing, retrieval, flashcards, quizzes, agents, tool use.

Related documents: `docs/AI_SECURITY.md`, `docs/AI_API_REFERENCE.md`, `docs/CONVERSATION_MANAGEMENT.md`, `docs/USAGE_AND_COST_TRACKING.md`, `docs/LLM_PROVIDER_INTEGRATION.md`
(which expands section 15), `docs/AI_TESTING.md`, `docs/AI_EVALUATION.md`.
