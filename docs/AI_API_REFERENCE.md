# AI API reference (Phase 2)

Base path `/api/v1`. The authoritative schema is the OpenAPI document at `/docs` (and `backend/openapi.json`);
the frontend types in `frontend/src/types/api.generated.ts` are generated from it. This page explains behaviour
the schema cannot.

## Conventions

- **Auth:** every endpoint needs a valid session cookie of an active user, otherwise 401. State-changing requests
  (POST, PATCH, DELETE) also need the `X-CSRF-Token` header (D-04), otherwise 403.
- **Envelope:** success `{"success": true, "data": ...}`; error `{"success": false, "error": {"code", "message"}}`.
  Error messages are generic and never contain provider text, prompts or credentials (D-49).
- **Ownership:** a conversation or message that does not exist **or belongs to someone else** returns the same 404.
- **No provider configured:** endpoints that need one return 503 `LLM_NOT_CONFIGURED`. `GET /ai/status` still answers 200.
- **Pagination:** `limit` (capped) and `offset`; lists are ordered by recent activity.

## Endpoints

| Method and path | Purpose | Success |
|---|---|---|
| `GET /ai/status` | Is AI configured? `configured`, `provider_display_name`, `is_test_provider`, `max_input_chars`. Works with no provider. | 200 |
| `GET /ai/models` | Enabled models (safe metadata only). | 200 |
| `GET /ai/models/default` | The default model. | 200 |
| `GET /ai/capabilities` | Capabilities of the provider and `provider_kind` (`real` or `test`). | 200 |
| `POST /ai/conversations` | Create. Body `{title?, model_id?}`. Works before any message. | 201 |
| `GET /ai/conversations` | List the caller's conversations. Query `status` (`active`/`archived`), `q` (title search, wildcards escaped), `limit`, `offset`. | 200 |
| `GET /ai/conversations/{id}` | One conversation. | 200 |
| `PATCH /ai/conversations/{id}` | Rename. Body `{title}` (1 to 200 chars, not blank). | 200 |
| `POST /ai/conversations/{id}/archive` | Archive (read-only afterwards). | 200 |
| `DELETE /ai/conversations/{id}` | Delete with its messages. Usage records are kept with their links set to null. | 204 |
| `GET /ai/conversations/{id}/messages` | Messages in order. Query `limit` (max 100), `offset`. Superseded answers carry `superseded_at`. | 200 |
| `POST /ai/conversations/{id}/messages` | Send a message. Body `{content, model_id?, stream}`. `stream: false` returns JSON (201); `stream: true` returns an SSE stream (200). | 201 / 200 |
| `POST /ai/conversations/{id}/messages/{message_id}/regenerate` | New answer for the **latest** answer only. Body `{model_id?, stream}`. The old answer is kept, marked superseded, and excluded from later context. | 201 / 200 |
| `POST /ai/conversations/{id}/messages/{message_id}/cancel` | Stop a running generation. Idempotent for a finished one. Only works on the instance running it (D-45). | 200 |
| `POST /ai/messages/{message_id}/feedback` | Rate a finished assistant answer. Body `{rating: "positive"\|"negative", feedback_text?}`. Re-rating replaces. | 200 |
| `GET /ai/usage` | The caller's usage records. Query `status` (`success`/`failed`/`cancelled`), `days`, `limit`, `offset`. | 200 |
| `GET /ai/usage/summary` | Totals over `days`. Unknown token or cost figures are counted separately, never as 0. | 200 |
| `GET /ai/usage/by-model` | Totals per model. | 200 |
| `POST /users/me/ai-notice/acknowledge` | Record that the privacy notice was acknowledged (idempotent). The time is `ai_notice_acknowledged_at` in `/users/me/preferences`. | 200 |

### Send message

Request: `{"content": "text", "model_id": null, "stream": false}`.
`content` is rejected with 422 `AI_INPUT_TOO_LONG` above `LLM_MAX_INPUT_CHARS` (default 8,000, reported by `/ai/status`)
or when blank. `model_id` must be one of `/ai/models` (else 422 `LLM_INVALID_MODEL`); omit it to use the default.

`stream: false` returns `data: {conversation_id, user_message, message, usage}`. `message.status` is `completed`.

`stream: true` returns `text/event-stream`. Before the first event, ownership, quota, size and context errors are normal
HTTP errors (JSON envelope with the status below). After it, failures arrive as `message.failed`.

| Event | Data |
|---|---|
| `message.started` | `message_id`, `user_message_id`, `conversation_id`, `model_id` |
| `message.delta` | `delta` (text) |
| `usage.updated` | `input_tokens`, `output_tokens`, `usage_source` (fields may be null), once at the end |
| `message.completed` | `message_id`, `finish_reason` |
| `message.failed` | `message_id`, `code`, `message` (generic) |
| `message.cancelled` | `message_id` |

A `: ping` comment line is sent every 15 s. Each `data:` is one line of JSON, so model text cannot break the framing.
Use `fetch` with `credentials: "include"` and the CSRF header; `EventSource` cannot POST. The client in
`frontend/src/features/ai-tutor/` shows a reference implementation. After any stream ends, re-read the messages: the
server is the source of truth.

### Message fields

`id, conversation_id, role (user|assistant), content, status (pending|streaming|completed|failed|cancelled),
sequence_number, model_id, prompt_key, prompt_version, input_tokens, output_tokens, usage_source
(provider_reported|estimated|unavailable), finish_reason, error_code, regenerates_message_id, superseded_at,
created_at, completed_at`. The system prompt is never returned.

### Usage record fields

`id, created_at, conversation_id, message_id, model_id, model_display_name, request_status, error_code, input_tokens,
output_tokens, reasoning_tokens, total_tokens, usage_source, estimated_cost, currency, pricing_version, duration_ms`.
`input_tokens`, `output_tokens` and `estimated_cost` are `null` when unknown. The UI shows "Unknown".

## Errors

| Status | Code | When |
|---|---|---|
| 401 | `NOT_AUTHENTICATED` (Phase 1 code) | No or invalid session |
| 403 | `CSRF_TOKEN_MISSING`, `CSRF_TOKEN_INVALID`, `CSRF_ORIGIN_MISMATCH` | Missing or wrong `X-CSRF-Token` on a state-changing request |
| 404 | `CONVERSATION_NOT_FOUND`, `MESSAGE_NOT_FOUND` | Missing **or not yours** |
| 409 | `AI_GENERATION_IN_PROGRESS` | A second send to a conversation that is already generating |
| 409 | `CONVERSATION_ARCHIVED` | Sending to an archived conversation |
| 409 | `AI_REGENERATE_NOT_ALLOWED` | Regenerating anything but the latest answer |
| 422 | `AI_INPUT_TOO_LONG`, `LLM_CONTEXT_TOO_LONG`, `LLM_INVALID_MODEL`, `LLM_CONTENT_BLOCKED`, validation errors | Bad input |
| 429 | `AI_QUOTA_EXCEEDED` (with `Retry-After`) | Per-minute rate, daily messages or tokens, or too many active generations per user |
| 429 | `LLM_RATE_LIMITED` | The provider is rate limiting |
| 502 | `LLM_AUTH_FAILED`, `LLM_BAD_RESPONSE` | Provider credential failure (the message says only "unavailable") or an unusable reply |
| 503 | `LLM_NOT_CONFIGURED`, `LLM_UNAVAILABLE` | No provider configured, or provider down |
| 504 | `LLM_TIMEOUT` | The provider took too long |

A failed or cancelled generation keeps its row (`status` failed or cancelled, partial content kept) and writes a usage
record with the matching `request_status`; it is never reported as a success. Retries (max 2, transient errors only) happen
only before the first streamed token.

## Phase 3 endpoints (documents and RAG)
Upload and manage: `POST /documents` (multipart), `GET /documents`, `GET|PATCH|DELETE /documents/{id}`, `POST /documents/{id}/archive|restore|retry|reprocess|cancel`, `GET /documents/{id}/status|processing|pages|content|download|inline`.
Search and sources: `POST /search`, `GET /documents/{id}/sources/{chunk_id}` (text and `regions`), `GET /citations/{id}`, `GET /ai/messages/{id}/citations`.
Conversations accept `scope` (`{kind, id}`) and `answer_mode`; streamed answers emit `message.citations` before the first `message.delta`. The authoritative list is `/docs` (OpenAPI).
