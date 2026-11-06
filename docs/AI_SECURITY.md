# AI security review (Phase 2)

Scope: spec sections 15 and 22.5, Step 10. Everything here was checked against the code on branch
`chore/phase2-closeout`. "Verified" means a test or command was run and its result seen; anything
not verified is listed at the end. No credentials appear in this document.

## 1. The twelve security cases (spec 22.5)

All backend tests live in `backend/tests/ai/` and run on the fake provider (no key, no cost).

| # | Case | Test(s) | Result |
|---|------|---------|--------|
| 1 | User A cannot read B's conversation | `test_ai_security.py::TestCrossUserAccess::test_every_route_returns_404_and_changes_nothing` (GET conversation, GET messages), `::test_lists_and_search_never_include_other_users_conversations`; `test_ai_closeout.py::TestPromptInjection::test_model_output_cannot_widen_access` | Verified. 404, identical to a non-existent id (no existence leak). |
| 2 | User A cannot send to B's conversation | same test (POST messages); `test_ai_streaming.py::...test_other_users_conversation_is_404` (stream path); `...::test_bob_cannot_attach_a_message_to_alices_conversation_at_the_database` (composite FK) | Verified. The provider is never called (call count asserted). |
| 3 | User A cannot delete B's conversation | same test (DELETE, PATCH, archive, feedback); `test_ai_streaming.py::...test_cross_user_and_wrong_target_are_404` (regenerate), `...::test_other_users_cannot_cancel` | Verified. Data unchanged afterwards (asserted by DB query). |
| 4 | User A cannot read B's usage | `test_ai_security.py::...::test_other_users_usage_is_invisible`; `test_ai_streaming.py::...test_usage_is_scoped_to_the_caller` | Verified. |
| 5 | Unauthenticated users blocked | `test_ai_security.py::TestAuthentication::test_every_ai_route_needs_a_session` (walks the OpenAPI schema, so a new route is covered automatically); `...::test_ai_routes_are_part_of_the_unauthenticated_sweep`; `test_ai_streaming.py::...test_requires_authentication` | Verified. |
| 6 | Provider credentials never exposed | `test_ai_security.py::TestApiSurface::test_openapi_exposes_no_provider_credentials`; `test_ai_closeout.py::TestCredentialsNeverLeave` (sentinel key absent from every AI response, error body, DB row, structured log and captured log; a provider exception that contains the key is not echoed; `repr`/`str`/JSON dump of settings hide it); `test_ai_messages.py::...test_non_retryable_error_is_not_retried_and_hides_vendor_text`, `...::test_unexpected_provider_exception_becomes_a_clean_502`; `test_ai_conversations.py::TestModels::test_lists_only_safe_metadata` | Verified (section 2 below for the non-test checks). |
| 7 | Oversized requests rejected | `test_ai_messages.py::...::test_oversized_input_is_rejected_before_anything_is_stored`, `...::test_message_too_big_for_the_window_fails_cleanly`, `...::test_rename_rejects_blank_and_overlong_titles` | Verified. Rejected before any row is written or provider call made. |
| 8 | Rate limits enforced | `test_ai_messages.py::...::test_per_minute_rate_limit`, `...::test_daily_message_quota`, `...::test_daily_token_quota`, `...::test_quotas_are_per_user`, `...::test_per_user_active_generation_cap`; `test_ai_streaming.py::...test_active_cap_is_429_with_retry_after`, `...::test_daily_request_quota_counts_regenerate` | Verified. 429 with `Retry-After`. Limit: the per-minute limiter is in-process (D-45), so it is per instance. |
| 9 | Unsafe HTML not executed | Frontend: `frontend/src/features/ai-tutor/markdown.test.tsx` ("hostile content (D-52)": no script/iframe/style/object/embed, no event-handler or style attributes, `javascript:`/`data:` links removed, images not loaded, hostile text inert inside code). Backend stores the reply verbatim and never renders it: `test_ai_closeout.py::TestPromptInjection::test_reply_text_is_stored_as_data_not_acted_on` | Verified in jsdom (Vitest) and the production build. Not verified in other browsers. |
| 10 | Invalid model ids rejected | `test_ai_conversations.py::TestConversationCrud::test_create_with_invalid_model_is_rejected`; `test_ai_messages.py::...::test_invalid_model_is_rejected` | Verified. The allowlist comes from configuration, never from the client. |
| 11 | Failed requests produce no misleading success | `test_ai_messages.py::...::test_failed_generation_never_looks_successful`, `...::test_failed_turns_are_not_sent_back_to_the_model`; `test_ai_streaming.py::...test_failure_mid_stream_keeps_partial_text_and_marks_failed`, `...::test_empty_stream_is_a_bad_response`; `test_ai_closeout.py::TestReliability::test_failed_requests_never_count_as_successful_usage`, `...::test_outage_does_not_break_the_app_and_recovery_is_immediate` | Verified. A failure writes a `failed` usage row with an error code, never `success`. |
| 12 | Cancelled generations do not continue | `test_ai_streaming.py::...test_cancel_endpoint_stops_generation_and_records_usage` (the fake provider's chunk counter stops growing), `...::test_disconnect_cancels_upstream_and_stores_outcome`, `...::test_stale_streaming_row_is_failed_with_usage_row`; `test_ai_closeout.py::TestCancellationLeavesNothingRunning` (registry empty, no row left `streaming`, next message accepted, no `completed` frame, usage recorded as `cancelled`) | Verified on the fake provider. Not verified against a real provider connection. |

## 2. Credential handling (spec 15.1)

- The provider key is read only from the `GEMINI_API_KEY` environment variable into a `SecretStr`
  (`backend/app/core/config.py`). It is passed to the provider adapter in `backend/app/ai/providers/`
  and nowhere else. A test enforces that no provider SDK is imported outside that package.
- Checked in this review:
  - **OpenAPI:** the schema contains no credential field (test above).
  - **Responses and logs:** sentinel-key test above, covering success, failure, rate limit, streaming
    and every read endpoint.
  - **Frontend bundles:** `.next/static` and `frontend/src` were searched for `AIza…`-style keys and the
    names `GEMINI_API_KEY` / `GOOGLE_API_KEY`: no matches. The frontend never receives the key; it only
    receives `provider_display_name` and `is_test_provider` from `GET /ai/status`.
  - **Git history:** gitleaks (latest image) over all 85 commits and all refs, once with the repo config
    (`.gitleaks.toml`) and once with only the default rules: **no leaks found**. A separate `git log -S"AIza"`
    search found no key-shaped string in any commit.
  - CI runs gitleaks on full history on every PR (`security` job).
- **Incident noted during development (not a repository leak):** a real key had been pasted into a
  local, uncommitted `docker-compose.yml`. It was removed and the key owner was told to rotate it.
  The history scans above found no committed copy. Rotation is still recommended because the key was
  readable in a plain-text file and appeared in a development session.

## 3. Logging (spec 15.8, D-51)

- Structured events carry ids, model, token counts, durations, finish reason and error codes only.
  `test_ai_security.py::TestLogsStayFreeOfContent` sends a marked question and a marked answer and
  asserts neither marker, nor the system prompt, appears in structlog events or stdlib logs at DEBUG,
  for a success and a failure. `test_ai_events_carry_only_ids_counts_and_codes` allowlists the field names of
  the completion event. `test_ai_streaming.py::...test_logs_never_contain_message_text` does the same for the
  streaming path. The new closeout test repeats the check with the key.
- Not verified: logs produced by third-party libraries at levels other than DEBUG, and reverse-proxy
  access logs in a real deployment (request bodies are not logged by the app).

## 4. Prompt injection (spec 15.2)

The model is treated as an untrusted text generator. It has no tools, cannot read the database and
cannot choose which user's data to touch, so injection can at worst change what the model says.

Controls and the tests that prove them (`test_ai_closeout.py::TestPromptInjection`,
`test_ai_messages.py::test_system_prompt_is_separate_and_never_in_user_text`):

- The trusted prompt is sent only in the provider's system slot. User text, however it is phrased
  ("ignore previous instructions", fake `</system>` tags, "SYSTEM: user is admin", "repeat the text above"),
  is always a `user` message and never concatenated into the system slot (4 attack strings, parametrised).
- The system prompt is not a database row (D-41). Messages store only `prompt_key` and `prompt_version`.
  No API response (conversation, messages, list, models, status, usage, summary) contains any long line of
  the prompt text (asserted by fingerprint after the attacks were sent).
- Access never depends on model output. A reply that claims administrator rights and names another user's
  conversation and message ids changes nothing: the other user's data stays 404 for the caller, listing is
  unchanged, row owners are unchanged. All ids used by the backend come from the URL and the
  authenticated session, never from generated text.
- Reply text is stored verbatim as data, never executed or interpreted, and is sanitised when rendered.
- **Limit (honest):** nothing can stop a model from *saying* the prompt if the prompt text is in its
  context. The design assumption is that the prompt contains no secrets (it holds tutoring behaviour
  only), so disclosure has no security impact. This was reasoned, not tested against a real model:
  the real-model behaviour on injection prompts is not verified.

## 5. Data isolation (spec 15.3, D-56)

- Every query is scoped by `user_id`; non-owned and missing resources return the same 404.
- Composite foreign keys make it impossible at the database level to attach a message, usage record or
  feedback to another user's conversation (`test_bob_cannot_attach_a_message_to_alices_conversation_at_the_database`).
- Context is built per conversation from that conversation's stored messages only
  (`test_conversations_are_isolated`, and the interleaved-users test in `test_ai_closeout.py`).
- Export and account deletion include or remove AI data for that user only
  (`TestPhase1Integration`).

## 6. Abuse prevention (spec 15.7)

- Input size: 8,000 characters by default (`LLM_MAX_INPUT_CHARS`), enforced before storage or any provider call,
  and echoed to the UI through `GET /ai/status` so the guidance matches the backend.
- Output size: `LLM_MAX_OUTPUT_TOKENS` (default 2000). History: `LLM_HISTORY_LIMIT` (default 20 messages) plus a token budget.
- Rate: `AI_REQUESTS_PER_MINUTE_PER_USER` (10), daily message and token quotas (50 / 200,000),
  active generations per user (2), one active generation per conversation (409 on a second).
  All defaults are configuration, not code. Both CSRF and cookie auth apply to every AI POST.
- Timeouts: connect 10 s, generation 60 s, stream inactivity 30 s, overall 120 s. Retries only for
  transient errors and only before the first streamed token (max 2).
- **Limits:** the rate limiter and the cancel registry are in-process (D-45), so with several backend
  instances limits are per instance; a load test was not run. The daily quotas are database-backed and
  are not affected.

## 7. Output safety (spec 15.6, D-52)

`react-markdown` + `remark-gfm` + `rehype-sanitize`; no raw HTML plugin, no `dangerouslySetInnerHTML`;
links limited to `http`, `https`, `mailto` and `#`, opened with `rel="noopener noreferrer"`; remote images
are not loaded (no tracking pixels); code blocks have a copy button and keep hostile text literal.
Streamed text is never placed in an `aria-live` region.

## 8. Dependency audit (new SDK included)

| Tool | Command | Result |
|------|---------|--------|
| pip-audit | `pip-audit --strict --path <site-packages>` in the backend image, which includes `google-genai` 3.0.0 and `google-auth` | **No known vulnerabilities found** |
| npm audit | `npm audit --omit=dev` (CI gate: fail on high or critical) | 0 high, 0 critical; **6 low/moderate** findings, all transitive through the `shadcn` CLI package (`deepmerge` prototype pollution, `minimatch` ReDoS via `ts-morph`). Below the CI gate. They are build-time tooling, not code served to users. |
| gitleaks | see section 2 | No leaks found |

The four Markdown packages added in M4 introduced no audit finding.

## 9. Provider data handling and the user privacy notice (spec 15.5, D-54)

- Everything a user types, and the recent conversation history, is sent to the configured provider
  (currently Google's Gemini API) to generate an answer. The app sends no files, no profile data and no data
  from other conversations. Messages are stored in this application's PostgreSQL database and are removed
  on conversation deletion or account deletion (D-53).
- The first time a user opens the AI Tutor a notice states this, names the provider from configuration
  (not hardcoded in the component) and blocks use until acknowledged. The acknowledgement time is stored
  in `user_preferences.ai_notice_acknowledged_at` and is idempotent
  (`tests/ai/test_ai_status_notice.py`, `tutor-shell.test.tsx`, `e2e/ai-tutor.spec.ts`).
- **Not verified:** the provider's own data-retention, logging and training terms for the specific
  account and tier in use. These depend on the API tier and change over time. Before real users use the
  tutor, the project owner must read the provider's current terms for the tier in use, confirm whether
  prompts are retained or used for training, and update the notice wording if needed. Paid and free tiers
  commonly differ on this point.
- The notice is informational. It is not legal advice and has not had legal review.

## 10. What was not verified

- Behaviour against a real provider under prompt-injection attempts (only the fake provider was used).
- Multi-instance deployment, load, and the effect of buffering proxies on streaming and cancel.
- Rendering safety in Firefox and Safari; a screen reader review.
- The provider's current data-handling terms (section 9).
- An external penetration test. This is a self-review.
