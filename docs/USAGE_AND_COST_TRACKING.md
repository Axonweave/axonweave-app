# Usage and cost tracking

What is recorded for each AI request, how cost is estimated, and the limits that cap consumption.
Code: `backend/app/ai/usage/pricing.py`, `backend/app/repositories/ai_usage_repository.py`,
`backend/app/modules/ai/service.py` (`UsageService`). Decisions: D-39, D-40, D-43.

## What is recorded

One `ai_usage_records` row for **every** provider call, whatever the outcome:

| Field | Notes |
|---|---|
| `request_status` | `success`, `failed` or `cancelled`. A failure is never recorded as a success. |
| `error_code` | Our code (for example `LLM_TIMEOUT`), never provider text. |
| `input_tokens`, `output_tokens`, `reasoning_tokens` | Nullable. **Null means unknown, never 0.** `output_tokens` includes reasoning tokens when the provider reports them. |
| `usage_source` | `provider_reported`, `estimated` or `unavailable`. |
| `estimated_cost`, `currency`, `pricing_version` | Null unless a verified price exists. The price version used is stored, so history is never recalculated. |
| `model_id`, `provider_id`, `duration_ms`, `provider_request_id` | Which model, how long. |

Message text is never stored in a usage row or logged. The row is written in the same transaction that finalises the message.
A stream cancelled before the provider reported usage is recorded as `unavailable` with null counts rather than a guess.

## Cost estimation (D-39)

`cost = input_tokens / 1M x input_price + output_tokens / 1M x output_price`, computed only when the price and both token counts are known. The price catalogue
(`PRICES` in `pricing.py`) is **empty until a price is verified** from the provider's published pricing page, and each entry carries the source URL and verification date.
Prices must not be entered from memory.

**Current state:** no prices are registered, so every real request has `estimated_cost = null` and the UI shows "Unknown". To enable costs: verify the price for the model in use,
add a `PriceEntry` (with `pricing_version`, `currency`, `source_url`, `verified_on`), and add a test. Existing rows keep their null cost; only new requests are priced.

## Viewing usage

- `GET /ai/usage` lists the caller's records (filter by status, window in days, paginated).
- `GET /ai/usage/summary` gives requests, failures, cancellations, token totals, how many requests had known tokens (`token_known_requests`) and known costs
  (`cost_known_requests`), and cost totals **per currency** (never summed across currencies).
- `GET /ai/usage/by-model` groups the same figures by model.
- The AI Tutor's "AI usage" dialog shows these. Everything is scoped to the signed-in user; another user's records are invisible (tested).

## Limits that cap consumption (all configurable)

| Control | Default | Behaviour |
|---|---|---|
| Requests per minute per user | 10 | 429 `AI_QUOTA_EXCEEDED` with `Retry-After`. In-process, so per backend instance (D-45). |
| Daily messages per user | 50 | 429. Counted from the database, so it survives restarts and works across instances. Regenerate counts. |
| Daily tokens per user | 200,000 | 429. From stored token counts (unknown counts are not guessed). |
| Active generations per user | 2 | 429. One per conversation is 409. |
| Input size | 8,000 characters | 422 `AI_INPUT_TOO_LONG`, before anything is stored or sent. |
| Output size | 2,000 tokens | `LLM_MAX_OUTPUT_TOKENS`. |
| Timeouts and retries | see `docs/LLM_PROVIDER_INTEGRATION.md` | |

Reference point from the first evaluation run (`docs/AI_EVALUATION.md`): about 1,200 tokens per request on average with `gemini-3.5-flash-lite`
(18,108 tokens over 15 requests). At that size 50 messages use about 60,000 tokens, so the message quota is reached before the token quota in short chats.
The defaults should be reviewed against real usage.

## Tests

`tests/ai/test_ai_streaming.py` (each outcome is listed and filterable; unknown stays unknown; a known price produces a cost; by-model and windows; usage scoped to the caller),
`tests/ai/test_ai_messages.py` (usage row has no message text; quotas are per user), `tests/ai/test_ai_closeout.py` (failed requests never count as success).
