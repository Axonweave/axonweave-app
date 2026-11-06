# Phase 2 acceptance (spec section 23)

Assessed 2026-11-06 on branch `chore/phase2-closeout`. Ratings:

- **Met**: implemented, and verified by an automated test or a check that was run (evidence named).
- **Partly**: something real exists and works, but part of the criterion is missing or unverified.
- **Not met**: not delivered.

"Fake provider" means the deterministic test provider, used by all automated tests. "Real provider" means Google Gemini
with model `gemini-3.5-flash-lite`, which was exercised through the smoke-test script, one live pytest, and the 15-request
evaluation run (`docs/AI_EVALUATION.md`). **No real-provider conversation was run through the browser UI.**

CI: pull request #15 (AI Tutor UI) was observed on GitHub with all four jobs green (backend, frontend, e2e, security) after
three e2e test fixes, and was merged. The three most recent runs on `main` were observed green on 2026-11-06. CI for this branch
(pull request #16) was observed with all four jobs green (backend, frontend, e2e, security) before merging.

## Overall

Phase 2 is **functionally complete on the fake provider and verified end to end with one real model through the API**, but it
is **not fully accepted**: answer quality has not been scored by a person, no cost can be computed because no model price is
verified, multi-instance behaviour is untested, and the real model has not been used through the browser. Tally:
**Met 37, Partly 5, Not met 0** (42 items). Items are "Partly" where a claim rests on something not verified, even if the
code path exists.

## LLM integration

| Criterion | Rating | Evidence / gap |
|---|---|---|
| At least one provider is successfully integrated | Met | Gemini adapter `backend/app/ai/providers/gemini_provider.py`; real streaming seen with `scripts/llm_smoke_test.py --stream`; 15 of 15 real requests succeeded in the evaluation run (`docs/ai_eval/results/2026-11-06_gemini-3.5-flash-lite_n15.csv`); adapter unit tests with a mocked transport in `tests/ai/test_provider_layer.py` |
| API keys are securely configured | Met | Environment variable into `SecretStr` only; `tests/ai/test_ai_closeout.py::TestCredentialsNeverLeave`; gitleaks over all history found nothing (`docs/AI_SECURITY.md` section 2). A key was once pasted in a local file and the owner was told to rotate it; that rotation has not been confirmed |
| Model configuration is centralised | Met | `backend/app/ai/model_registry.py` plus environment variables; no model id literal in code (D-38); `test_provider_layer.py` registry tests |
| Provider-specific code is isolated | Met | `test_provider_layer.py::test_no_provider_sdk_imported_outside_providers_package` |
| Normal text generation works | Met | Real: smoke test and the evaluation run (15 successes, all finish reason `stop`). Fake: `test_ai_messages.py::TestSendMessage` |
| Provider errors are handled | Met | Every taxonomy code mapped and tested with a mocked transport (`test_provider_layer.py`); service behaviour in `test_ai_messages.py::TestFailures`, `test_ai_closeout.py::TestReliability::test_outage_does_not_break_the_app_and_recovery_is_immediate`. Real errors also seen and mapped during development (unknown model, timeout). Provider auth failure against the real service was not forced |
| Timeouts are configured | Met | `LLM_*_TIMEOUT_SECONDS` in `backend/app/core/config.py`, passed in every request; a real timeout was observed and mapped to `LLM_TIMEOUT` during model selection; a short generation timeout is shown to map to `LLM_TIMEOUT` in `test_provider_layer.py`. The stream-inactivity timeout is configured but has no dedicated test |

## AI Tutor

| Criterion | Rating | Evidence / gap |
|---|---|---|
| User can start a conversation | Met | `e2e/ai-tutor.spec.ts`: "a suggested prompt sends a real request and creates a conversation"; `test_ai_conversations.py::TestConversationCrud` |
| User can submit a question | Met | e2e streaming test; `test_ai_messages.py`. Fake provider in the browser |
| Assistant can respond | Met | Fake provider in the browser; real provider through the API (evaluation run). Not through the browser |
| Streaming works | Partly | Fake provider in the browser: e2e "text streams in progressively, with Stop shown meanwhile, then completes"; backend `test_ai_streaming.py`. Real Gemini streaming verified by the smoke test and the live test, not in the browser, and not behind a buffering proxy |
| Follow-up questions retain context | Partly | Context is built and sent correctly (`test_ai_messages.py::test_follow_up_keeps_earlier_turns_in_order`, e2e follow-up test). Whether the real model uses it well is not judged: two follow-up pairs were run in the evaluation but not scored |
| Conversation history is persisted | Met | e2e "after a refresh the whole history is still there, from the server"; `test_ai_conversations.py` |
| User can switch between conversations | Met | e2e "a chosen conversation opens from the drawer and the drawer closes" and sidebar highlight test |
| User can rename conversations | Met | e2e "rename updates the sidebar, the header and the server"; `test_ai_conversations.py` |
| User can delete conversations | Met | e2e "archive removes it from the list; delete asks first and removes it for good"; `test_ai_security.py::TestPhase1Integration` |
| User can stop generation | Met | e2e "Stop cancels the answer, keeps what arrived and records a cancelled request"; `test_ai_streaming.py` cancel and disconnect tests; `test_ai_closeout.py::TestCancellationLeavesNothingRunning`. Fake provider |

## Context and prompts

| Criterion | Rating | Evidence / gap |
|---|---|---|
| System prompt is centrally managed | Met | `backend/app/ai/prompts/` registry synced to `prompt_templates` (D-41); `test_ai_schema.py` |
| Prompt version is recorded | Met | `prompt_key` and `prompt_version` on every assistant message; `test_ai_messages.py` (version asserted) and the evaluation CSV records them |
| Conversation history is included appropriately | Met | `test_ai_messages.py`: order, history limit, failed turns excluded, superseded answers excluded |
| Context limits are enforced | Met | `test_ai_messages.py::test_budget_drops_oldest_whole_turns`, `::test_message_too_big_for_the_window_fails_cleanly`; `test_ai_closeout.py::test_long_conversation_stays_within_the_context_budget` |
| Conversations remain isolated | Met | `test_ai_messages.py::test_conversations_are_isolated`; `test_ai_closeout.py::test_interleaved_users_never_see_each_others_context` |
| No unsupported file or academic context is invented | Partly | The backend sends only the conversation and the prompt, which tells the model not to claim access to files (`academic_tutor` v1); no file or workspace data is ever sent (tests above). Whether a real model obeys that was not evaluated |

## Usage

| Criterion | Rating | Evidence / gap |
|---|---|---|
| Input tokens are recorded where available | Met | `usage_source = provider_reported` in the real run (CSV); unknown stays null: `test_ai_streaming.py::test_summary_treats_unknown_as_unknown` |
| Output tokens are recorded where available | Met | Same. Reasoning tokens are included in the output figure when the provider reports them |
| Model usage is recorded | Met | One usage row per call with model, status and duration: `test_ai_messages.py::test_usage_record_written_without_message_text`, `test_ai_streaming.py::TestUsageEndpoints` |
| Estimated costs are calculated when pricing data is available | Partly | The calculation is tested with a known price (`test_ai_streaming.py::test_known_price_produces_cost`), but **no real price is registered**, so no real request has a cost; the UI shows "Unknown" (verified in e2e). This is the intended behaviour until a price is verified (D-39) |
| Users can view their own usage | Met | `test_ai_streaming.py::test_usage_is_scoped_to_the_caller`; e2e "usage shows real figures, and 'Unknown' (never 0) for cost" |
| Configurable request limits are enforced | Met | `test_ai_messages.py`: per-minute, daily message and token quotas, per-user and per-conversation concurrency; `test_ai_streaming.py` 429 with `Retry-After`. Per-minute limiter is in-process, so per instance |

## Security

| Criterion | Rating | Evidence / gap |
|---|---|---|
| Provider keys remain on the backend | Met | Not in OpenAPI, responses, DB rows, logs, the production frontend build, or git history (`docs/AI_SECURITY.md` sections 1 and 2) |
| AI endpoints require authentication | Met | `test_ai_security.py::TestAuthentication` (walks the OpenAPI schema, so new routes are covered) |
| Conversation ownership is verified | Met | `test_ai_security.py::TestCrossUserAccess` (every route 404, nothing changed, indistinguishable from not found); e2e second-user test |
| User data is isolated | Met | Same, plus composite foreign keys (`test_bob_cannot_attach_a_message_to_alices_conversation_at_the_database`) and export/deletion tests |
| Input limits are implemented | Met | `test_ai_messages.py::test_oversized_input_is_rejected_before_anything_is_stored`; limit shown in the UI from `/ai/status` |
| Rate limiting works | Met | `test_ai_messages.py::test_per_minute_rate_limit` and quota tests. Single instance only |
| Generated content is rendered safely | Met | `markdown.test.tsx` hostile cases; e2e "model output is rendered safely: hostile HTML never runs" in Chromium. Other browsers not tested |
| Sensitive content is excluded from logs | Met | `test_ai_security.py::TestLogsStayFreeOfContent`, `test_ai_streaming.py::test_logs_never_contain_message_text`, the key check in `test_ai_closeout.py`. Application logs only; proxy and third-party logs not reviewed |

## Quality

| Criterion | Rating | Evidence / gap |
|---|---|---|
| Tests pass | Met | Observed locally on this branch: backend 464 passed and 2 skipped (they need `docs/`, which the container does not mount), coverage 96%, ruff, format and mypy clean, one Alembic head; Vitest 200 passed; Playwright on a fake-provider stack with CI's AI rate limit: 105 passed, 21 skipped by design, 0 failed. A first run with the default 10/min AI limit had 3 failures (one AI spec and two Phase 1 specs on the mobile project); the AI spec passed alone and the full suite passed on rerun, so the Phase 1 failures are unexplained and unconfirmed. CI observed green on PR #15 and `main` (see top) |
| AI responses are evaluated | Partly | A 40-question set, a capped runner and one 15-request real run exist, with latency and tokens recorded. **No person has scored the answers**, so correctness and hallucination are unknown (`docs/AI_EVALUATION.md`) |
| Provider failures do not crash the application | Met | `test_ai_closeout.py::test_outage_does_not_break_the_app_and_recovery_is_immediate`; `test_ai_messages.py::test_unexpected_provider_exception_becomes_a_clean_502`; failed stream keeps partial text |
| Database persistence works | Met | Messages, usage, feedback survive reload (e2e) and restarts (the sweeper test `test_stale_streaming_row_is_failed_with_usage_row`); schema tests |
| Documentation is updated | Met | The seven documents of spec section 25 exist (`AI_ARCHITECTURE`, `LLM_PROVIDER_INTEGRATION`, `AI_API_REFERENCE`, `CONVERSATION_MANAGEMENT`, `AI_SECURITY`, `USAGE_AND_COST_TRACKING`, `AI_TESTING`) plus `AI_EVALUATION`; `README.md` and `docs/WORKFLOW.md` updated. No credentials appear in them |

## Open items (what stops this being a clean "complete")

1. A person must score the evaluation answers (`docs/ai_eval/results/...csv`), then decide whether the model and prompt are good enough.
2. Verify the model's published price and add it to the pricing registry so cost becomes real (D-39).
3. Try a real conversation through the browser, with the real key, before real users.
4. Confirm the provider's data-handling terms for the tier in use and adjust the privacy notice if needed (`docs/AI_SECURITY.md` section 9).
5. Rotate the Gemini key that was exposed during development and confirm.
6. Multi-instance deployment: move the rate limiter and cancel registry out of process before running more than one backend instance (D-45).
7. Not tested: Firefox, Safari, real phones, screen readers, buffering proxies, load, a conversation of several hundred messages in the UI.
8. Frontend dependency audit: 6 low/moderate findings via the `shadcn` CLI package, below the CI gate (`docs/AI_SECURITY.md` section 8).
