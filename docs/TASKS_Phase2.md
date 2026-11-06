# Task board and ownership (Phase 2: AI foundation)

Spec step numbers refer to `PHASE2_SPEC.md` section 21. Design: `AI_ARCHITECTURE.md`. Decisions: `DECISIONS.md` D-37 to D-61.
Tick a task only when its PR is merged to `main`. Ownership is filled in when work is assigned.
One branch per task, Conventional Commits, no push to `main`, one Alembic head.

## Shared files (change minimally, mention in the PR)
`backend/app/api/v1/router.py`, `backend/app/main.py`, `backend/app/models/__init__.py`, `backend/requirements.txt`,
`docker-compose.yml` (every new env var must be added under `backend.environment`; there is no `env_file`), `.env.example`,
`frontend/package.json`, `backend/app/modules/users/service.py` (export), `frontend/src/components/layout/app-sidebar.tsx`.

## Preconditions
- [ ] PRs #6 to #8 (Phase 1 closeout, security deps, subjects UI) merged and `main` green in CI, including E2E.
- [ ] This planning PR (`docs/phase2-plan`) merged.
- [ ] A Gemini API key available to the developer as `GEMINI_API_KEY` in their own local `.env` (never committed, never pasted into a PR or chat). Provider-side spending limit set to a small development budget.

## M1: Provider layer + AI database (spec Steps 3, 4)  Owner: ________
- [ ] Settings: `LLM_*`, `AI_*` variables, `GEMINI_API_KEY` as `SecretStr`, production guards (no `fake` in production, no placeholder key). Pass-through added to `docker-compose.yml`; placeholders added to `.env.example`.
- [ ] `ai/types.py`, `ai/errors.py` (taxonomy D-49), `ai/providers/base.py` (interface, capabilities), `ai/model_registry.py`.
- [ ] `ai/providers/registry.py`, `fake_provider.py` (D-60: refuses to start unless `development`/`testing`, explicit opt in), `gemini_provider.py` (pinned `google-genai`, D-57).
- [ ] `scripts/list_llm_models.py` (D-38). Run it with the real key; **record the chosen model id and the verification date** in `docs/LLM_PROVIDER_INTEGRATION.md` and D-38.
- [ ] Verify current Gemini pricing on Google's pricing page; add the pricing registry and record the date and `pricing_version` (D-39). Unknown means NULL.
- [ ] Models: `llm_providers`, `llm_models`, `llm_model_prices`, `prompt_templates`, `conversations`, `messages`, `message_feedback`, `ai_usage_records`; `user_preferences.ai_notice_acknowledged_at`. All constraints on the models (D-61): partial unique index, composite FKs, CHECKs, `ON DELETE SET NULL (col)` (verify emit; fallback documented).
- [ ] Alembic migration(s); `alembic heads` shows one. Grants for `axonweave_app` verified with `has_table_privilege`.
- [ ] Startup sync of model registry and prompts (D-37, D-41).
- [ ] Tests: provider contract tests for Gemini adapter with a mocked transport (valid, invalid credentials, normal, streaming, timeout, rate limit, invalid model, malformed response, missing usage); fake provider scenarios; import-boundary test (no SDK outside `ai/providers/`); schema tests (constraints on model, migrated schema equals metadata, app-role grants, one active generation per conversation, cross-owner rows rejected, SET NULL keeps usage rows).
- [ ] One real request from the backend to Gemini in a marked `live` test or manual run; token usage verified against the provider's reported figures.
- Done when: Axonweave can talk to the provider, AI data persists, ruff/mypy/pytest pass, nothing user-facing yet.

## M2: Conversations, messages, context, non-streaming generation (Steps 5, 6)  Owner: ________
- [x] Conversation APIs: create, list (paginated, search, last activity order), get, rename, archive, delete; all scoped by `user_id`, 404 for non-owned (D-56).
- [x] Message APIs: list, send (non-streaming), feedback. Sequence numbers under a conversation row lock (D-42). Deterministic title (D-55).
- [x] `ContextManager` (D-47): budget, complete turns, estimate flag, `LLM_CONTEXT_TOO_LONG`, ignores superseded/failed/cancelled rows.
- [x] `PromptRegistry` with `academic_tutor` v1; `prompt_key`/`prompt_version` recorded on each assistant message (D-41).
- [x] `AiService` with retry policy (D-50) and error mapping; failed and cancelled messages never look successful.
- [x] `/ai/models`, `/ai/models/default`, `/ai/capabilities` (safe metadata only); `LLM_NOT_CONFIGURED` 503 path (D-58).
- [x] Input length limit; per-user request-rate limit (existing limiter).
- [x] Export (`/users/me/export`) and account deletion include AI data (D-53); tests for both.
- [x] Tests: ownership for every endpoint (cross-user 404, nothing changed), unauthenticated 401 sweep, follow-up context retention, context isolation, limits respected, oversized input, invalid model, provider failure paths, no secret or content in logs, delete conversation keeps usage rows with NULL ids.
- Done when: multi-turn conversations work end to end on the fake provider and on the real one.
  - Status: met on the fake provider (automated). NOT yet verified on the real provider: waiting for the
    M1 key run (`scripts/llm_smoke_test.py`) and then one manual multi-turn check.
  - Note: streaming and usage endpoints were added in M3.

## M3: Streaming, cancellation, regenerate, usage and quotas (Steps 8, 9)  Owner: ________
- [x] Spike first: stream through the real middleware stack and disconnect mid-stream. If `BaseHTTPMiddleware` interferes, convert CSRF, correlation id and security headers middleware to pure ASGI before continuing.
- [x] SSE endpoint (D-44): events per spec 12.3, heartbeat, headers, periodic partial flush, final persistence, failures after start as `message.failed`.
- [x] Cancellation (D-45): registry, cancel endpoint, disconnect handling with shielded cleanup, upstream call cancelled.
- [x] Regenerate (D-42) with `superseded_at`; duplicate-click protection via the partial unique index and per-user cap (D-43).
- [x] Stale generation recovery at startup and periodically (D-46).
- [x] Usage recording on every outcome; reasoning tokens; `usage_source`; cost from the pricing registry with `pricing_version`; NULL when unknown (D-39, D-40).
- [x] Quotas: daily messages and tokens, active-generation cap; 429 `AI_QUOTA_EXCEEDED` with `Retry-After` (cross-conversation cap); same-conversation double send stays 409.
- [x] Usage endpoints (`/ai/usage`, `/summary`, `/by-model`), owner-scoped.
- [x] Tests: ordering, heartbeat, cancel, disconnect, partial persistence, failure after start, retries only before first token, concurrent sends (one wins, others 409), quota enforcement, usage accuracy against fake provider figures, other user's usage invisible.
- Done when: users see progressive output, can stop it, and consumption is measurable and capped.
  - Status: met on the fake provider (automated, 37 tests). NOT verified: real Gemini streaming (needs the
    user's key: `python scripts/llm_smoke_test.py --stream`, then `pytest -m live`), multiple processes, load,
    real browsers, buffering proxies.
  - Spike result: the existing `BaseHTTPMiddleware` stack streams progressively (first chunk 0.18 s), keeps
    Cache-Control / X-Accel-Buffering / correlation id, and an abrupt disconnect reaches the generator within
    0.05 s. No conversion to pure ASGI was needed.
  - Limit (D-45): the generation registry (cancel endpoint) and rate limiter are in-process, so cancel by endpoint
    works only on the instance running the generation. A disconnect still cancels on any instance, and the
    sweeper (D-46) recovers rows left by a dead instance after `ai_stale_generation_seconds`.

## M4: AI Tutor UI (Step 7 + streaming client)  Owner: ________
- [x] Enable the sidebar item (D-59); update Vitest and Help text. Route `(app)/ai-tutor` and `[conversationId]`.
- [x] Conversation sidebar (new, list, search, rename, delete with confirmation, date grouping), chat window, input (Enter sends, Shift+Enter newline, Stop button, length guidance), header with model selector only when more than one model.
- [x] Safe Markdown rendering (D-52); copy, regenerate, thumbs up/down.
- [x] Fetch-based SSE client with CSRF header, abort, partial-failure handling, retry, server refetch as source of truth.
- [x] Welcome screen with suggested prompts that really send; "not configured" state (D-58); first-use privacy notice and acknowledgement (D-54); test-provider badge (D-60); usage summary view.
- [x] Loading, empty and error states; responsive to 375 px with no horizontal scroll; keyboard accessible with visible focus.
- [x] Vitest for components and the stream parser; Playwright on the fake provider: start chat, stream, stop, regenerate, follow-up, rename, delete, switch, reload persistence, second-user isolation, mobile.
- Done when: the whole spec section 1.3 flow works in the browser.
  - Status: built and verified on the fake provider (see below). NOT verified: a real Gemini conversation in the browser, real screen readers, Safari/Firefox, real phones (only Chromium at 375 px and Pixel 5 emulation), long conversations (>100 messages are loaded in pages of 100 but not stress-tested), and behaviour behind buffering proxies.
  - Verified: 200 Vitest tests (125 existing + 75 new: parser, stream client, hostile Markdown, input, message view, hook, shell gates); 21 Playwright tests x2 projects (`e2e/ai-tutor.spec.ts`) plus the whole Phase 1 e2e suite (105 passed, 21 skipped, 0 failed); `next build` (production) succeeds.
  - Backend changes made for the UI (small, tested): `GET /ai/status`; `POST /users/me/ai-notice/acknowledge` and `ai_notice_acknowledged_at` on preferences (D-54; column existed since 0002); `FAKE_LLM_CHUNK_DELAY_SECONDS` (fake provider only) so the e2e Stop test can press Stop mid-stream.
  - Known limits: the thumbs up/down state is kept in the page only (the message API does not return stored feedback), so it resets on reload; leaving the page mid-answer disconnects, which the server records as a cancel (D-45); no math rendering (D-52 allows it only if it works under the CSP); archived conversations are archived from the UI but there is no "archived chats" view yet.
  - Found by the browser tests (fixed): `usePathname()` in the shared app layout broke `next build` under Cache Components; after Stop, the client could keep showing a stale `pending` answer until it re-read the server (it now re-reads until the answer is no longer active).

## M5: Security review, evaluation, docs, acceptance (Steps 10, 11, spec 25)  Owner: ________
- [x] Security review against spec 15 and 22.5 (all twelve cases mapped to named tests) in `docs/AI_SECURITY.md`; gitleaks (full history, with and without the repo config), `pip-audit` (includes `google-genai`), `npm audit`, and a frontend bundle/source scan for key patterns were run.
- [x] Prompt-injection tests: user text cannot reach the system slot, the API never returns prompt text, model output cannot change access (`backend/tests/ai/test_ai_closeout.py`).
- [~] Evaluation set (spec 18): 40 questions, a capped runner (`backend/scripts/run_ai_eval.py`), one 15-request real run on `gemini-3.5-flash-lite` with latency and tokens recorded (`docs/AI_EVALUATION.md`). **Answer quality is NOT scored**; the scoring columns are blank for a human reviewer. Cost is unknown (no verified price).
- [x] Load and failure tests: provider outage then recovery, rate limit, stream failure and interruption, concurrent sends (one user), 60-turn conversation, interleaved users, nothing left running after cancel. A multi-user parallel or load test was not run.
- [x] Documentation (spec 25): `AI_ARCHITECTURE.md` (updated), `LLM_PROVIDER_INTEGRATION.md` (includes the OpenAI-compatible adapter steps for Qwen or Llama; the adapter itself is not built), `AI_API_REFERENCE.md`, `CONVERSATION_MANAGEMENT.md`, `AI_SECURITY.md`, `USAGE_AND_COST_TRACKING.md`, `AI_TESTING.md`; `README.md` and `docs/WORKFLOW.md` updated. No credentials in any of them.
- [x] Acceptance checklist for spec section 23 written honestly: `docs/PHASE2_ACCEPTANCE.md` (see its tally and open items).
- [ ] CI: backend and E2E jobs green on `main` (observed green for PR #15 and the three latest `main` runs on 2026-11-06); this branch's CI to be observed.
- Done when: every section 23 criterion is met or honestly listed as open. Open items are listed at the end of `PHASE2_ACCEPTANCE.md` (human scoring, price verification, real browser run, provider terms, key rotation, multi-instance).

## Out of scope (do not start)
Everything in Phase 2 spec section 24: document parsing, OCR, chunking, embeddings, vector DB, RAG, flashcards, quizzes, spaced repetition, knowledge graph, learner intelligence, research extraction, audio, agents, tool execution, multi-agent orchestration.
