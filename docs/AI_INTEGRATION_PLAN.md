# AI integration plan: review of Phase 1 (Phase 2, spec Step 1)

Status: plan, no feature code. Written on branch `docs/phase2-plan`.
Source: `docs/PHASE2_SPEC.md` (Step 1), `docs/PHASE1_SPEC.md` sections 13 to 15 and 17, and a read of the repository.
Companion: `docs/AI_ARCHITECTURE.md` (the design), `docs/DECISIONS.md` D-37 onward, `docs/TASKS_Phase2.md`.

Rule for everything below: Phase 2 **extends** Phase 1. No working Phase 1 module is replaced.

## 1. Baseline (before any Phase 2 work)

Run on branch `feat/ui-subjects-folders-chapters` (PRs #6 to #8, not yet merged) on 2026-11-06.

| Check | Result |
|---|---|
| Backend `ruff check`, `ruff format --check` | clean (97 files) |
| Backend `mypy app` | clean (76 source files) |
| Backend `pytest` | 251 passed |
| Frontend `tsc --noEmit`, `eslint` | clean |
| Frontend Vitest | 125 passed (12 files) |
| Frontend `next build` | compiles |

One trap: two `pytest` runs at the same time share one test database and produce hundreds of errors. Run one at a time.

## 2. How Phase 1 works today

### 2.1 Backend core (`backend/app/core`)

| File | What it does today | Phase 2 consequence |
|---|---|---|
| `config.py` | `pydantic-settings` `Settings` (`extra="ignore"`, `lru_cache` `get_settings()`). `AppEnv` is `development`, `testing`, `production`. A `model_validator` refuses insecure production config (cookie, placeholder secret, https URL, placeholder DB password). Secrets are plain `str` today. | Add LLM and quota settings. Provider keys use `SecretStr`. Add production guards (see 4.1). `extra="ignore"` means an env var that is not declared is silently unreachable. |
| `dependencies.py` | `get_current_user` (cookie to `AuthService`), `require_active_user`, `require_verified_user`; aliases `CurrentUser`, `ActiveUser`, `VerifiedUser`; `DbSession`. | AI routes use `ActiveUser` (D-16: unverified users may use academic features). Nothing new needed. |
| `csrf.py` | `CSRFMiddleware(BaseHTTPMiddleware)`: for non-safe methods with a session cookie, checks Origin/Referer against `FRONTEND_URL` and the `X-CSRF-Token` double submit. | The streaming POST passes through it unchanged because it sends the header. See the streaming risk in 2.4. |
| `rate_limit.py` | `RateLimiter` protocol plus `InProcessRateLimiter` (fixed window, string keys, raises HTTP 429 with `RATE_LIMIT_EXCEEDED` and `Retry-After`). Per process (D-18). | Reuse for per-user request limits (new key prefixes). Same single-instance limitation, documented. |
| `security_logging.py` | One function per event on the `security` logger (`log_login_failure`, `log_rate_limit_hit`, ...). No content, ids only. | Add AI events (quota hit, blocked content, auth failure to the provider) in the same style. |
| `security_headers.py` | `SecurityHeadersMiddleware`: `nosniff`, `Referrer-Policy`, `Cache-Control: no-store` on API responses. | SSE needs `no-store` (already) plus `X-Accel-Buffering: no`; set on the streaming response itself. |
| `logging.py` | `structlog` setup, `CorrelationIdMiddleware` (sanitised id), JSON logs in production. | Add `provider_request_id`, `model`, token counts, durations to log context. Never content (D-51). |
| `security.py`, `email.py` | Argon2id, token hashing, `EmailSender` interface. | Unchanged. `EmailSender` is the precedent for the provider interface plus a console/fake implementation. |

### 2.2 Application wiring

- `main.py`: `FastAPI` with a `lifespan` that only configures logging. Middleware order: CORS (outermost), CSRF, CorrelationId, SecurityHeaders. Exception handlers normalise `HTTPException`, `RequestValidationError` and any `Exception` into `{"success": false, "error": {"code", "message"}}`. The lifespan is where D-37 (model/prompt sync) and D-46 (stale generation recovery) will run.
- `api/v1/router.py`: one `APIRouter`, `include_router` per module. AI adds its routers here (a shared file, mention in the PR).
- Success envelope: `{"success": true, "data": ...}`; list endpoints add `total` beside `data`.
- Errors are raised as `HTTPException(detail={"code": ..., "message": ...})`. AI errors follow the same shape (D-49).

### 2.3 Database

- `database/base.py`: `Base`, `UUIDPrimaryKeyMixin`, `TimestampMixin` (timezone-aware UTC, server default `now()`).
- `models/__init__.py` imports every model so Alembic sees the metadata. New AI models must be added there.
- Alembic: `env.py` reads `DATABASE_MIGRATION_URL` (the owner role), `target_metadata = Base.metadata`. One migration so far (`0001_initial_schema`), exactly one head required.
- Roles (D-33): `init-db.sql` creates `axonweave_app` with `SELECT, INSERT, UPDATE, DELETE` and sequence usage, using `ALTER DEFAULT PRIVILEGES`. Default privileges only apply to tables created **by the role that ran the statement**. The migrations run as `axonweave_owner`. **Not yet verified**: that tables created by a later migration get the app-role grants. M1 must check with `has_table_privilege` and add explicit `GRANT`s in the migration if needed.
- The test suite connects with the **owner** role (`DATABASE_TEST_URL`), so a missing grant for `axonweave_app` would not be caught by tests. M1 adds a test that connects as the app role.
- The test suite builds the schema with `Base.metadata.create_all`, not migrations. Constraints that exist only in a migration (partial unique indexes, composite FKs, CHECKs) are invisible to tests. Rule for Phase 2 (D-61): every constraint is declared on the model, and CI compares the migrated schema with the metadata.

### 2.4 Request pipeline risk for streaming

`CSRFMiddleware`, `CorrelationIdMiddleware` and `SecurityHeadersMiddleware` all subclass `BaseHTTPMiddleware`. That base class wraps the response body and complicates streaming and client-disconnect propagation. Streaming (M3) starts with a spike test: stream through the real middleware stack, disconnect mid-stream, confirm the handler is cancelled. If it fails, convert the three middlewares to pure ASGI. They are small (86, 92 and 42 lines).

### 2.5 Repository and module pattern

Layering is `route -> service -> repository -> model`, schemas at the edges.

- `modules/<name>/routes.py`, `service.py`, `schemas.py`; `repositories/<name>_repository.py`; `models/<name>.py`.
- Every query is scoped by owner. Subjects, folders and chapters join up to `workspaces.user_id`. Non-owned resources return 404.
- Services raise `HTTPException` with a code and message; services take the `AsyncSession` and commit.
- The spec's top-level `services/` and `schemas/` folders exist but are empty. They stay empty; AI code follows the `modules/` pattern.

### 2.6 Tests (`tests/conftest.py`)

- Session-scoped `create_test_tables` (create_all / drop_all), autouse `clean_db`, `db_session`, `client` (overrides `get_db`), helpers `_make_user` and `_make_session`, fixture `create_user_and_session`. 251 tests, coverage gate 85% in CI.
- Provider tests use a mocked or fake provider. No test may call a real provider. Live-provider tests are optional, marked, and skipped unless a key is present.

### 2.7 Account export (D-24) and deletion (D-23)

- `UserService.export_data` builds a dict from `ExportRepository` methods (workspaces, subjects, folders, chapters, activity). It is hand-written: **AI data is not exported until we add it** (D-53).
- `UserService.delete_account` re-checks the password, marks `deletion_requested`, revokes sessions, then `await db.delete(user)`. Cascades come from ORM relationships on `User` plus `ON DELETE CASCADE` foreign keys. AI tables must use `ON DELETE CASCADE` from `users.id` and need no ORM relationship on `User`.

### 2.8 Frontend

- `lib/api/client.ts`: `fetch` with `credentials: "include"`, reads the `csrf_token` cookie into `X-CSRF-Token` for non-safe methods, parses the envelope, throws `ApiRequestError(code, message, status)`. It calls the backend directly (`NEXT_PUBLIC_BACKEND_URL`), so there is no proxy to buffer a stream.
- `next.config`: CSP with `connect-src 'self' <backend>`, `script-src 'self' 'unsafe-inline'`. Streaming to the backend is allowed. Markdown rendering must not need anything more permissive.
- Routes live in the `(app)` group (protected layout) and `(auth)`. The spec says `(dashboard)`; see section 3.
- `components/layout/app-sidebar.tsx`: "AI Tutor" is a disabled "Coming soon" item (D-26). A Vitest test asserts it is disabled and not focusable, and `help/page.tsx` says it is coming soon. Enabling it changes the test and the help text (D-59).
- API types are generated from OpenAPI (`npm run generate-types`); AI endpoints appear there automatically. The SSE stream is not in OpenAPI and needs a hand-written typed event schema in `features/ai`.
- Existing reusable pieces for the chat UI: `Dialog`, `ConfirmDialog`/`DestructiveDialog`, `RowActions`, `Pager`, `EmptyState`, `ErrorDisplay`, `useAsync`, `useToast`.

### 2.9 Docker and environment

- `docker-compose.yml` lists each backend variable explicitly under `environment:` with `${VAR:-default}`. There is **no `env_file`**. Any new `LLM_*`, `GEMINI_API_KEY` and `AI_*` variable must be added there or it never reaches the container. This is a shared file (M1 task, mention in the PR).
- The backend image is a development image (`uvicorn --reload`, single worker). In-process state (rate limiter, cancellation registry) is therefore per process (D-45).
- `.env.example` holds placeholders only. In this session `.claude/settings.json` denies reading `.env.*`, which also blocks editing `.env.example`; the placeholder block for Phase 2 is in section 6 for a maintainer to paste.

## 3. Where the spec disagrees with the repo, and how we adapt

| Spec says | Repo has | Adaptation |
|---|---|---|
| Frontend route group `(dashboard)` | `(app)` | Put AI routes in `(app)/ai-tutor`. |
| `modules/ai/{conversations,messages,usage,models}` and top-level `ai/` | `modules/` per feature; `ai/` has only `__init__.py` | Same layout: `modules/ai/<sub>/{routes,service,schemas}.py`; `ai/` holds providers, orchestration, prompts, usage. |
| Provider files `openai_provider.py`, `anthropic_provider.py`, `local_provider.py` | none | Only `base.py`, `registry.py`, `gemini_provider.py`, `fake_provider.py` now (D-37, spec 5.2). |
| Spec 13.1 `messages.model_id VARCHAR` | no AI tables | Keep `VARCHAR` (internal model id, survives model row changes); usage rows reference `llm_models.id`. |
| Spec 13.1 `messages.prompt_version` only | n/a | Add `prompt_key` beside it (D-41). |
| Spec 9.3 statuses (pending, streaming, completed, failed, cancelled) | n/a | Unchanged. "Superseded" is a separate nullable `superseded_at`, not a status (D-42). |
| Spec 12.1 "SSE" | `EventSource` cannot POST or send headers | fetch-based SSE over POST (D-44). |
| Spec 26 "no fake AI output" | n/a | `FakeProvider` only in `development` and `testing`, explicit opt in, visible badge (D-60). |
| Spec 5.5 example uses `OPENAI_API_KEY` | n/a | `GEMINI_API_KEY`; other providers declare their own settings inside their adapter. |
| Spec `Tool` message role "reserved" | n/a | Allowed in the role CHECK, never produced in Phase 2. |
| Phase 1 spec 23 and CLAUDE.md rule 12 forbid LLM work | rule 12 in force | Replaced by Phase 2 rules (CLAUDE.md update in this PR). Phase 2 spec section 24 items stay forbidden. |
| Phase 1 D-26: AI Tutor disabled | disabled | D-59 amends it. |

## 4. Integration plan

### 4.1 Configuration

New settings (all optional so the app runs without a provider, D-58):
`LLM_PROVIDER`, `LLM_DEFAULT_MODEL`, `LLM_ALLOWED_MODELS`, `GEMINI_API_KEY` (`SecretStr`), timeouts, limits, retries, quotas (names in section 6).

Production guards added to `Settings._production_guards`: refuse `LLM_PROVIDER=fake`; refuse a placeholder key when a provider is set.
`FakeProvider` additionally refuses to start unless `APP_ENV` is `development` or `testing`, as a second check at construction time.

### 4.2 Code layout (what gets added)

```
backend/app/ai/
  errors.py            LLMError hierarchy and codes
  types.py             LLMRequest, LLMResponse, Usage, stream event types, Capabilities
  model_registry.py    ModelConfig, registry built from settings, no SDK imports
  providers/
    base.py            LLMProvider interface
    registry.py        provider factories, the only place that maps a name to an adapter
    gemini_provider.py the ONLY file importing google-genai
    fake_provider.py   tests and local UI development only
  orchestration/
    ai_service.py      generate/stream use cases
    context_manager.py budget and history selection
    generation_registry.py  in-process cancellation registry (D-45)
    recovery.py        stale generation sweeper (D-46)
  prompts/
    registry.py, academic_tutor.py (versioned source files), sync to prompt_templates
  usage/
    pricing.py, cost_calculator.py, token_tracker.py, quotas.py
backend/app/modules/ai/{conversations,messages,usage,models}/{routes,service,schemas}.py
backend/app/models/{conversation,message,message_feedback,llm_provider,llm_model,llm_model_price,ai_usage_record,prompt_template}.py
backend/app/repositories/{conversation,message,usage,...}_repository.py
backend/scripts/list_llm_models.py   (D-38)
```

An import-boundary test (M1) fails the build if any file outside `app/ai/providers/` imports `google`, `openai`, `anthropic` or another provider SDK.

### 4.3 Shared files touched (mention in the PR)

`api/v1/router.py`, `main.py` (lifespan: sync and recovery), `models/__init__.py`, `docker-compose.yml` (env pass-through), `.env.example`, `requirements.txt` (one pinned SDK), `users/service.py` (export), `app-sidebar.tsx` and its test, `help/page.tsx`, `frontend/package.json` (markdown libraries, D-52).

### 4.4 Database plan

New tables, all with UUID keys, UTC timestamps, FKs, indexes and explicit delete behaviour. Full column list and constraints: `docs/AI_ARCHITECTURE.md` section 8. One new nullable column on `user_preferences` (`ai_notice_acknowledged_at`, D-54).

### 4.5 Risks and how the milestones handle them

| Risk | Handling |
|---|---|
| Constraints only in migrations are not tested | D-61: constraints on models; schema-drift check in CI. |
| App-role grants on new tables | Verified in M1, tested as the app role. |
| `BaseHTTPMiddleware` and streaming | Spike first in M3, convert to pure ASGI if needed. |
| SET NULL on a column list of a composite FK | Verify SQLAlchemy and Alembic emit `ON DELETE SET NULL (col)` on PostgreSQL 16 in M1; fallback is an explicit service step. |
| Provider model IDs and prices change | Never hardcoded; verified at setup with `list_llm_models.py`; dates recorded (D-38, D-39). |
| In-process state with several workers | Documented limit (D-45). Per-user active cap uses the database. |
| Provider cost during development | Strict dev quotas by default, `FakeProvider` for UI work, mocked tests for CI. |

## 5. Out of scope in Phase 2

Everything in Phase 2 spec section 24 (document parsing, OCR, chunking, embeddings, vector DB, RAG, flashcards, quizzes, spaced repetition, knowledge graph, research extraction, audio, agents, tool execution, multi-agent). The `tool` role and `generate_structured` exist only as interface hooks.

## 6. Environment variable placeholders (for `.env.example`)

Placeholders only. Paste into `.env.example`; each also needs a line under `backend.environment` in `docker-compose.yml`.

```env
# --- AI (Phase 2) ---
# Leave LLM_PROVIDER empty and the app runs with the AI Tutor showing "not configured".
LLM_PROVIDER=
# Provider model id. Verify it with: docker compose exec backend python scripts/list_llm_models.py
LLM_DEFAULT_MODEL=
# Optional comma-separated extra provider model ids users may pick
LLM_ALLOWED_MODELS=
# Optional verified limits of the default model (see list_llm_models.py output)
LLM_MODEL_MAX_INPUT_TOKENS=
LLM_MODEL_MAX_OUTPUT_TOKENS=
GEMINI_API_KEY=

LLM_CONNECT_TIMEOUT_SECONDS=10
LLM_GENERATION_TIMEOUT_SECONDS=60
LLM_STREAM_INACTIVITY_TIMEOUT_SECONDS=30
LLM_OVERALL_TIMEOUT_SECONDS=120
LLM_MAX_RETRIES=2
LLM_MAX_OUTPUT_TOKENS=2000
LLM_MAX_INPUT_CHARS=8000
LLM_HISTORY_LIMIT=20
LLM_THINKING_BUDGET=

AI_MAX_ACTIVE_GENERATIONS_PER_USER=2
AI_REQUESTS_PER_MINUTE_PER_USER=10
AI_DAILY_MESSAGE_QUOTA=50
AI_DAILY_TOKEN_QUOTA=200000
AI_STALE_GENERATION_SECONDS=300
```

Defaults are deliberately conservative for development spending (spec "three decisions", item 2). Raise them per environment.
