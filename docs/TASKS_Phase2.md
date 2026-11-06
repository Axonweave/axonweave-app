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
- [ ] Conversation APIs: create, list (paginated, search, last activity order), get, rename, archive, delete; all scoped by `user_id`, 404 for non-owned (D-56).
- [ ] Message APIs: list, send (non-streaming), feedback. Sequence numbers under a conversation row lock (D-42). Deterministic title (D-55).
- [ ] `ContextManager` (D-47): budget, complete turns, estimate flag, `LLM_CONTEXT_TOO_LONG`, ignores superseded/failed/cancelled rows.
- [ ] `PromptRegistry` with `academic_tutor` v1; `prompt_key`/`prompt_version` recorded on each assistant message (D-41).
- [ ] `AiService` with retry policy (D-50) and error mapping; failed and cancelled messages never look successful.
- [ ] `/ai/models`, `/ai/models/default`, `/ai/capabilities` (safe metadata only); `LLM_NOT_CONFIGURED` 503 path (D-58).
- [ ] Input length limit; per-user request-rate limit (existing limiter).
- [ ] Export (`/users/me/export`) and account deletion include AI data (D-53); tests for both.
- [ ] Tests: ownership for every endpoint (cross-user 404, nothing changed), unauthenticated 401 sweep, follow-up context retention, context isolation, limits respected, oversized input, invalid model, provider failure paths, no secret or content in logs, delete conversation keeps usage rows with NULL ids.
- Done when: multi-turn conversations work end to end on the fake provider and on the real one.

## M3: Streaming, cancellation, regenerate, usage and quotas (Steps 8, 9)  Owner: ________
- [ ] Spike first: stream through the real middleware stack and disconnect mid-stream. If `BaseHTTPMiddleware` interferes, convert CSRF, correlation id and security headers middleware to pure ASGI before continuing.
- [ ] SSE endpoint (D-44): events per spec 12.3, heartbeat, headers, periodic partial flush, final persistence, failures after start as `message.failed`.
- [ ] Cancellation (D-45): registry, cancel endpoint, disconnect handling with shielded cleanup, upstream call cancelled.
- [ ] Regenerate (D-42) with `superseded_at`; duplicate-click protection via the partial unique index and per-user cap (D-43).
- [ ] Stale generation recovery at startup and periodically (D-46).
- [ ] Usage recording on every outcome; reasoning tokens; `usage_source`; cost from the pricing registry with `pricing_version`; NULL when unknown (D-39, D-40).
- [ ] Quotas: daily messages and tokens, active-generation cap; 429/409 with `Retry-After`.
- [ ] Usage endpoints (`/ai/usage`, `/summary`, `/by-model`), owner-scoped.
- [ ] Tests: ordering, heartbeat, cancel, disconnect, partial persistence, failure after start, retries only before first token, concurrent sends (one wins, others 409), quota enforcement, usage accuracy against fake provider figures, other user's usage invisible.
- Done when: users see progressive output, can stop it, and consumption is measurable and capped.

## M4: AI Tutor UI (Step 7 + streaming client)  Owner: ________
- [ ] Enable the sidebar item (D-59); update Vitest and Help text. Route `(app)/ai-tutor` and `[conversationId]`.
- [ ] Conversation sidebar (new, list, search, rename, delete with confirmation, date grouping), chat window, input (Enter sends, Shift+Enter newline, Stop button, length guidance), header with model selector only when more than one model.
- [ ] Safe Markdown rendering (D-52); copy, regenerate, thumbs up/down.
- [ ] Fetch-based SSE client with CSRF header, abort, partial-failure handling, retry, server refetch as source of truth.
- [ ] Welcome screen with suggested prompts that really send; "not configured" state (D-58); first-use privacy notice and acknowledgement (D-54); test-provider badge (D-60); usage summary view.
- [ ] Loading, empty and error states; responsive to 375 px with no horizontal scroll; keyboard accessible with visible focus.
- [ ] Vitest for components and the stream parser; Playwright on the fake provider: start chat, stream, stop, regenerate, follow-up, rename, delete, switch, reload persistence, second-user isolation, mobile.
- Done when: the whole spec section 1.3 flow works in the browser.

## M5: Security review, evaluation, docs, acceptance (Steps 10, 11, spec 25)  Owner: ________
- [ ] Security review against spec 15 and 22.5 (all twelve cases mapped to named tests): auth, ownership, keys never exposed (including OpenAPI and error bodies), input limits, rate limits, safe rendering, cancellation, logging review, provider data handling.
- [ ] Prompt-injection tests: user text cannot change the system prompt or access control; model-supplied ids are never trusted.
- [ ] Evaluation set (spec 18): questions across the listed subject areas, criteria table, manual review, results recorded with provider, model id, prompt version, date; compare only on identical settings.
- [ ] Load and failure tests: concurrent requests, provider outage, stream failure, long conversations.
- [ ] Documentation (spec 25): `AI_ARCHITECTURE.md` (update), `LLM_PROVIDER_INTEGRATION.md`, `AI_API_REFERENCE.md`, `CONVERSATION_MANAGEMENT.md`, `AI_SECURITY.md`, `USAGE_AND_COST_TRACKING.md`, `AI_TESTING.md`. No credentials in any of them.
- [ ] Acceptance checklist for spec section 23 written honestly (met / partly met / not met), like `PHASE1_ACCEPTANCE.md`.
- [ ] CI: backend and E2E jobs green on `main`; migration drift check; coverage gate still met.
- Done when: every section 23 criterion is met or honestly listed as open.

## Out of scope (do not start)
Everything in Phase 2 spec section 24: document parsing, OCR, chunking, embeddings, vector DB, RAG, flashcards, quizzes, spaced repetition, knowledge graph, learner intelligence, research extraction, audio, agents, tool execution, multi-agent orchestration.
