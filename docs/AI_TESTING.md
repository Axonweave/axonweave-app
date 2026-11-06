# AI testing

How the AI layer and the AI Tutor are tested, how to run each suite, and what is deliberately not covered.
Rules: ordinary tests run on the **fake provider** (no network, no key, no cost); real-provider tests are
optional, marked `live`, and never run in CI.

## Run the tests

```bash
# Backend (one pytest at a time: the tests share one database)
docker compose exec backend pytest -m "not live" tests/ai          # AI suite only
docker compose exec backend pytest -m "not live"                   # everything, with the 85% coverage gate in CI
docker compose exec backend sh -c "ruff check . && ruff format --check ."
docker compose exec backend mypy app

# Frontend
cd frontend && npm run lint && npx tsc --noEmit && npm run test   # Vitest
npm run build                                                       # production build must succeed

# Browser (Playwright). The stack must run with the fake provider (see below)
cd frontend && PW_EXTERNAL_STACK=1 npx playwright test e2e/ai-tutor.spec.ts
```

**Use `-m "not live"` whenever a key is configured in your environment.** `tests/ai/test_live_streaming.py` is marked
`live`, is skipped without a key, but runs (and sends one real request) if a key is present and you do not exclude it.

### Browser tests against the fake provider

Start the backend with `LLM_PROVIDER=fake` and `FAKE_LLM_CHUNK_DELAY_SECONDS=0.1` (CI sets both for the e2e job). Variables set in
your shell override `.env` in Docker Compose. Do not run the browser tests against a real provider: they send many messages.
Registration and login are rate limited per IP, so the specs present distinct client IPs; that needs `TRUST_PROXY_HEADERS=true`
on the test stack only (see `docs/SETUP.md`). To go back to your normal setup afterwards, run `docker compose up -d backend` without
those variables set.

### Optional live tests and scripts (cost money, use your key)

```bash
docker compose exec backend python scripts/list_llm_models.py          # names only
docker compose exec backend python scripts/llm_smoke_test.py --stream  # one request
docker compose exec backend pytest -m live tests/ai                    # live streaming through the real SSE endpoint
docker compose exec backend python scripts/run_ai_eval.py --help       # answer-quality evaluation, see docs/AI_EVALUATION.md
```

## What each suite covers

| Spec 22 area | Where |
|---|---|
| 22.1 Provider (credentials, normal and streaming generation, timeout, rate limit, invalid model, malformed response, missing usage) | `backend/tests/ai/test_provider_layer.py` (adapter with a mocked transport, error taxonomy, registry, import boundary: no provider SDK outside `app/ai/providers/`) |
| 22.2 Conversations (create, list, rename, get, delete, archive, persistence) | `test_ai_conversations.py` |
| 22.3 Messages (send, persist both, order, failed, cancelled, regenerate, duplicate submission) | `test_ai_messages.py`, `test_ai_streaming.py` |
| 22.4 Context (follow-ups, isolation, limits, old messages, system prompt separate, user text cannot override) | `test_ai_messages.py`, `test_ai_closeout.py::TestPromptInjection` |
| 22.5 Security (12 cases) | Mapped one by one in `docs/AI_SECURITY.md` |
| 22.6 Frontend (rendering, new chat, select, submit, streaming, stop, retry, copy, rename, delete, mobile) | Vitest in `frontend/src/features/ai-tutor/*.test.ts(x)`; Playwright in `frontend/e2e/ai-tutor.spec.ts` (desktop Chromium plus a Pixel 5 "Mobile Chrome" project) |
| Schema and database rules (constraints, composite foreign keys, partial unique index, grants, migration drift) | `test_ai_schema.py` and the Phase 1 migration tests |
| Streaming (framing, heartbeat, event order, disconnect, cancel, partial persistence, failure after start, retries only before the first token) | `test_ai_streaming.py` |
| Usage, cost and quotas | `test_ai_streaming.py`, `test_ai_messages.py`, `test_ai_closeout.py` |
| Reliability (outage then recovery, long conversation, interleaved users, nothing left running after cancel) | `test_ai_closeout.py::TestReliability`, `::TestCancellationLeavesNothingRunning` |
| Status endpoint and privacy notice | `test_ai_status_notice.py`, `tutor-shell.test.tsx` |
| Evaluation runner (caps, selection, output) | `test_ai_eval_script.py` |
| Hostile Markdown and HTML | `markdown.test.tsx` |
| Stream parser and client | `sse.test.ts`, `use-chat.test.ts` |

The ordinary suites use mocked provider responses, as the spec requires (18.4), so they cost nothing.

## Test fixtures worth knowing

- `ai` fixture (`tests/ai/conftest.py`): swaps in a runtime with generous limits and the fake provider; `ai.configure(...)` changes a setting for one test
  and `ai.use(provider)` swaps the provider.
- `FakeProvider` knobs: `reply`, `chunk_size`, `chunk_delay`, `fail_with`, `fail_after_chunks`, `malformed`, `report_usage`, `delta_usage`, plus `calls` (the requests it
  received) and `chunks_sent` (proves a cancelled stream really stopped). It refuses to run when `APP_ENV` is `production`.
- An autouse fixture in `backend/tests/conftest.py` removes `LLM_*`, `GEMINI_API_KEY` and `FAKE_LLM_CHUNK_DELAY_SECONDS` from the environment so a developer's
  configured key or fake-provider setting cannot change test results.

## Celery in tests (Phase 3)

Tasks run **eagerly**, in the test process with no broker, through the `celery_eager` fixture (`tests/conftest.py`):

```python
def test_health_task_runs_eagerly(celery_eager):
    assert ping.delay().get() == {"status": "ok"}
```

- Exceptions propagate to the test (`task_eager_propagates`). The fixture switches eager mode off again afterwards.
- A task that wraps its own `asyncio.run` (the storage-cleanup and sweep tasks) cannot be called from inside an async test. Test the service
  function it wraps (`process_outbox`, `ProcessingJobRepository.fail_stale_running`), as `tests/ingestion/test_celery_and_outbox.py` does.
- `tests/__init__.py` sets `RATE_LIMIT_BACKEND=memory`, `STORAGE_BACKEND=` and `EMBEDDING_PROVIDER=` before anything imports the app, so the suite never
  uses the stack's Redis or object store by accident. The real values are kept in `tests.AMBIENT_STORAGE` / `AMBIENT_REDIS_URL` for the few tests that
  need them: the S3 storage contract tests (they **fail instead of skipping when `CI` is set** and no endpoint is configured) and one real-Redis limiter test.
- Migration tests (`tests/documents/test_migration.py`) run the real `alembic` command against a throwaway database and compare constraint, index and column
  names with the schema built from the models.

## Known limits of the tests

- **No real-provider test runs in CI.** Real streaming was verified by hand with `llm_smoke_test.py --stream` and the optional live test, once, on one model.
- **Cross-user requests cannot be fired in parallel in a backend test:** the test client shares one database session, so truly parallel requests from two users interleave
  incorrectly. Concurrency is tested for one user (double submit, active-generation cap) and the e2e suite covers two users in separate browser sessions, but a
  multi-user load test was not run.
- The rate limiter and cancel registry are in-process, so multi-instance behaviour is not tested (D-45).
- Playwright runs in Chromium (desktop and a Pixel 5 emulation). Firefox, Safari, real phones, screen readers and buffering proxies were not tested.
- No coverage measurement exists for the frontend.
- Answer quality is not an automated test: see `docs/AI_EVALUATION.md`; scoring is manual.
