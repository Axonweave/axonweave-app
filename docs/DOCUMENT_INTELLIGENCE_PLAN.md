# Document Intelligence: review of Phase 1 and 2 and integration plan (Phase 3, Part A)

Written 2026-11-06 on branch `docs/phase3-plan`. Source of requirements: `PHASE3_SPEC.md`. Design: `DOCUMENT_ARCHITECTURE.md`.
Decisions: `DECISIONS.md` D-62 onward. Tasks: `TASKS_Phase3.md`. This document describes the code **as it is today** in the areas
Phase 3 touches, then lists conflicts with the spec and how they are adapted. Nothing here is implemented yet.

## 0. Baseline (before any Phase 3 work)

| Check | Result |
|---|---|
| CI on `main` | Green: the three latest `main` runs (PR #17, #16, #15), newest 2026-11-06 15:58Z |
| Backend `pytest` (container) | 467 passed, 2 skipped (they need `docs/`, which the container does not mount) |
| `ruff check`, `ruff format --check`, `mypy app` | Clean (148 files formatted, 111 source files typed) |
| `alembic heads` | One head: `0002` |
| Frontend `npm run lint` / Vitest | Clean / 200 passed |
| Frontend `npm run format:check` | **Warns on 29 files** (pre-existing; CI does not run this script; not caused by this branch; left alone) |
| Playwright e2e | **Not run locally.** Relied on CI, which ran it green on this commit |

## 1. How the code works today, area by area

### 1.1 Config (`backend/app/core/config.py`)
Pydantic `Settings`, secrets as `SecretStr`, `APP_ENV` guard (`fake` provider refused outside development/testing). Each provider has its
own small settings class so core `Settings` ignores provider variables (AI_ARCHITECTURE 6.1). **Phase 3:** add storage, Redis, Celery,
embedding, ingestion-limit and retrieval settings in the same style, with production guards (no placeholder keys, no fake embedder).

### 1.2 `docker-compose.yml`
Services: `postgres` (`postgres:16-alpine`, init scripts mount `infrastructure/docker/init-db.sql` and `init-test-db.sh`), `mailpit`,
`backend`, `frontend`. There is **no `env_file`**: every variable must be listed under `backend.environment` (as `LLM_*` are). The backend
mounts `./backend:/app`, so `docs/` is not visible in the container. **Phase 3:** replace the Postgres image with a pgvector build; add
`redis`, `worker`, `beat` and an S3 emulator; pass every new variable through; worker gets no outbound network (see D-70).

### 1.3 CI (`.github/workflows/ci.yml`)
Jobs: backend (Postgres service `postgres:16-alpine`, ruff, mypy, `alembic upgrade head`, one-head check, pytest with coverage >= 85%),
frontend (lint, tsc, Vitest, build), e2e (full compose stack, `LLM_PROVIDER=fake`, Playwright chromium), security. **Phase 3:** the backend
service image must provide pgvector; add a Redis service for rate-limiter tests; e2e needs the worker and object store in the stack;
`format:check` should be added only after the existing 29 warnings are fixed (separate chore, not part of Phase 3).

### 1.4 Alembic and the restricted role (D-33)
`alembic/env.py` reads `DATABASE_MIGRATION_URL` (owner role), runs async, `compare_type` and `compare_server_default` on. Two migrations exist
(`0001` initial, `0002` AI tables). The app connects as `axonweave_app` (DML only). `init-db.sql` grants DML on current tables and sets
`ALTER DEFAULT PRIVILEGES` for tables created later by the owner, plus sequence usage. Consequences for Phase 3:
- `CREATE EXTENSION vector` needs privileges the app role lacks; do it in a migration run by the owner (D-62). The `vector` type and operators
  are usable by the app role once the extension exists (it needs `USAGE` on the schema where it lives; keep it in `public`).
- New tables inherit grants via default privileges, but D-61 requires a test that connects as `axonweave_app` and checks them, which stays.
- Generated columns, GIN indexes and the partial unique index must be declared on the model (D-61: tests build the schema with `create_all`),
  and "migrated schema equals metadata" in CI must still pass with the `vector` type (needs `pgvector` Python package registered in
  `env.py` and the test comparison).

### 1.5 `ai/` orchestration, provider registry, usage
- `ai/providers/base.py` defines `LLMProvider`; `registry.py` maps name to factory; only `providers/` imports vendor SDKs (a test enforces it).
- `ai/orchestration/`: `service.py` (`AiService`: retries, error mapping), `context.py` (`ContextManager` with `ContextSource` objects, so a
  document source can be added without changing callers), `streaming.py` (SSE events, heartbeat, partial flush, `GenerationRegistry`),
  `runtime.py` (settings + registry + lazy provider; tests override), `recovery.py` (stale generations).
- `ai/prompts/` is versioned source synced to `prompt_templates`; assistant rows record `prompt_key`/`prompt_version`.
- `ai/usage/pricing.py`: pricing registry, empty today so cost is NULL.
- **Phase 3 reuse:** RAG becomes a new `ContextSource` plus a new prompt key (`rag_document_*`), not a new chat path. Embedding calls get their
  own provider interface (`EmbeddingProvider`, D-69) and extend the import-boundary test to cover it.

### 1.6 Message and SSE flow
`POST /ai/conversations/{id}/messages` (JSON or SSE). Ownership check, model resolve, quotas, one transaction that inserts the user message and
a `pending` assistant row (conversation row locked, `sequence_number` assigned, partial unique index = one active generation), context build,
provider stream, periodic flush, final persistence plus a usage row. Events today: `message.started`, `message.delta`, `usage.updated`,
`message.completed`, `message.failed`, `message.cancelled`. **Phase 3:** add `message.citations` before the first delta; `message.completed`
gains validated text and citations (D-75). Retrieval happens before `message.started`, so retrieval errors stay ordinary HTTP errors.

### 1.7 Conversations and messages model
`conversations` has `user_id`, `title`, `status`, `model_id`, `last_message_at`, `UNIQUE(id, user_id)`; messages use composite FKs to it. No
scope concept exists. **Phase 3:** `scope_type`/`scope_id` on `conversations` (CHECK + service ownership validation) and the scope used per
message, new `message_citations` table (D-67), `request_kind` on `ai_usage_records` (D-67).

### 1.8 Rate limiter and chat cancellation registry
- `core/rate_limit.py`: `RateLimiter` Protocol with one in-process sliding-window implementation, module singleton `get_rate_limiter()`,
  `reset()` for tests. Used by auth routes, email routes, users routes, and `AiService`. **Phase 3:** `RedisRateLimiter` behind the same
  Protocol (D-65); in-process stays for tests and development.
- `GenerationRegistry` (`streaming.py`): in-process map of message id to task. Stays in the API process (D-45 stands). Ingestion jobs use
  their own cancel mechanism (DB flag + Celery revoke), not this registry.

### 1.9 Account deletion and export (`modules/users/service.py`)
`delete_account` re-authenticates, sets `deletion_requested`, revokes sessions, then deletes the user synchronously; everything else goes by FK
cascade. `export_data` assembles profile, preferences, workspaces, subjects, folders, chapters, activity, `ai_conversations`, `ai_usage`
through `export_repository`. **Phase 3 problem:** an FK cascade cannot delete S3 objects. Before the user row is deleted, the service must
write `storage_cleanup` rows (no FK to the user) in the same transaction (D-66); export adds `documents` metadata only (D-66).

### 1.10 Sidebar and routes
`components/layout/app-sidebar.tsx`: **Library** is in `comingSoonNav` (disabled). Route group is **`(app)`**, not the spec's `(dashboard)`.
Existing pages: `dashboard`, `workspaces`, `workspaces/[workspaceId]/subjects/[subjectId]` and `.../chapters/[chapterId]`, `subjects`,
`ai-tutor` and `[conversationId]`, `activity`, `archived`, `settings`, `help`. Features live in `src/features/` (`academic`, `ai-tutor`, ...).
D-59 pattern applies: enabling Library changes the sidebar, its Vitest assertion and the Help text in the same PR.

### 1.11 Subjects, folders, chapters pages (upload targets)
Verified to exist: the subject page and the chapter page are nested under `workspaces/[workspaceId]/subjects/[subjectId]`. **There is no
separate folder page**: folders are shown inside the subject page (feature code in `features/academic`). So uploads can attach to workspace,
subject, folder and chapter, but the "folder" UI is a section, not a route. Documents get a `workspace_id` plus either subject, folder or
chapter (see conflicts, section 2).

### 1.12 CSP and headers (`frontend/next.config.ts`)
CSP: `default-src 'self'`, `script-src 'self' 'unsafe-inline'`, `img-src 'self' data: blob:`, `connect-src 'self' <backend>`,
`frame-ancestors 'none'`, no `frame-src`/`worker-src`/`object-src`. `X-Frame-Options: DENY`. No-store only for `/(dashboard|workspaces|subjects|settings)`;
`ai-tutor` and any new `library`/`documents` path are **not** covered. Phase 3 impact:
- pdf.js needs a worker: add `worker-src 'self' blob:` (or a same-origin worker file) and keep `script-src` strict.
- Inline PDF viewing via an `<iframe>` or `<object>` is blocked (`default-src` falls back for `frame-src`, and `X-Frame-Options: DENY`
  applies to the backend response too). We use pdf.js with `fetch` of bytes from the backend instead (D-72); no iframe needed.
- Add `/(library|documents|ai-tutor)(.*)` to the no-store rule.
- Backend inline and download endpoints set their own headers (D-64, D-72).

## 2. Conflicts between `PHASE3_SPEC.md` and the repo, and how we adapt

| # | Spec says | Repo / decision says | Adaptation |
|---|---|---|---|
| 1 | Route group `(dashboard)` (20) | The group is `(app)` | Use `(app)/library`, `(app)/documents/[documentId]`. Spec names are illustrative |
| 2 | Components in `components/documents/` | Features live in `src/features/<name>` with shared UI in `components/` | Put document UI in `features/documents` (and `retrieval`, `citations` only if they grow); reuse `components/ui` |
| 3 | `documents.deleted_at` soft deletion (18.1) | D-10: hard delete, no soft-delete columns | Hard delete + cascade + storage outbox (D-66). Spec 21.5 "delete or invalidate" is satisfied by deletion |
| 4 | `subject_id` optional on documents | Subjects belong to a workspace; folders and chapters belong to a subject (D-09) | Require `workspace_id`; allow `subject_id`, `folder_id`, `chapter_id` with composite FKs so the chain is always consistent (folder and chapter must belong to the subject; subject to the workspace) |
| 5 | Signed URLs for downloads (5.2, 21.1) | CLAUDE.md rule 1: authorise in the backend, return 404 for non-owned | Stream through the backend after an ownership check; presigned URLs are off by default (D-64). Spec test 9 "signed URLs expire" becomes "no public URL exists; download needs a session" unless presigned is enabled later |
| 6 | `document_chunks` has no `user_id`; filters by workspace etc. (11.1) | CLAUDE.md rule 3: every query scoped by owner; D-56 composite-FK pattern | Add `user_id` with composite FK `(document_id, user_id)` (D-67) |
| 7 | `document_chunks.document_version` integer | Versions are rows in `document_versions` | Chunks reference `document_version_id` (FK) and keep the integer number for display; unique `(document_version_id, chunk_index)` |
| 8 | `processing_status` on `documents` and on versions and jobs | Needs one source of truth | Version status is authoritative; job stage drives progress; `documents.processing_status` is a denormalised copy (D-68) |
| 9 | Status list includes "Uploaded", "Validating" | Validation happens synchronously in the upload request | Keep all spec names in the enum, but `validating` is only a worker-side re-check; a rejected upload never creates a row (422) |
| 10 | `/search/semantic`, `/search/hybrid`, `/search/documents/{id}` as separate endpoints (19.3) | One retrieval service | Expose one `POST /search` with `mode` (`semantic`/`keyword`/`hybrid`) and optional `document_id`; thin aliases only if the frontend needs them. Saves surface to secure and test |
| 11 | RAG request carries `context.scope_type/scope_id/answer_mode` per message (19.4) | Scope should be stable per conversation (16.2 "preserve the scope") | Store scope on the conversation; messages may only carry `answer_mode`, and a scope change is a new conversation or an explicit PATCH, validated server-side. Each message records the scope actually used |
| 12 | `document_chat_scopes` table (18.6) | Conversation columns are simpler | `scope_type`, `scope_id` on `conversations` with CHECK (D-67); no extra table |
| 13 | `document_embeddings` table optional (18.5) | Spec says choose one | Embeddings stay on `document_chunks`; model, dimensions and `index_version` recorded per chunk (D-69) |
| 14 | `extracted.json` and `processing-metadata.json` in storage (5.1) | Extracted text lives in chunks/DB | Store only originals in object storage; extracted structure is in DB. Fewer objects to delete and no second copy of content |
| 15 | "No Redis" (CLAUDE.md, D-18, README) | Spec 2 requires Redis + Celery | Update CLAUDE.md, README, D-18 (superseded by D-65) |
| 16 | Spec section 24 out-of-scope list | Same intent as CLAUDE.md rule 12 for Phase 2 | New CLAUDE.md Phase 3 rule keeps section 24 out of scope. Note: "full study-guide generation" and "flashcards" belong to Phase 4 |
| 17 | `request_kind` absent from usage | Embedding calls also cost tokens/money | Add `request_kind` (`chat`/`embedding`/`generation`) to `ai_usage_records` (D-67) so embedding usage is visible and quota-able |
| 18 | Antivirus "where available" (4.6) | No scanner in stack | `Scanner` interface, ClamAV off by default, fail-closed when enabled (D-71) |
| 19 | Docker: single language stack | Worker needs Tesseract, PyMuPDF, python-docx etc. | Separate worker image target in `backend/Dockerfile` (same code, extra OS packages), so the API image stays small and has no OCR binaries |
| 20 | Spec 12.5 retrieval evaluation / test dataset | No copyrighted material in git | Generated fixtures in code; real documents in ignored `testdata-private/` (D-76) |

## 3. Risks found during the review

1. **Storage and DB divergence on cascade deletes** (account/workspace/subject/folder/chapter deletion all cascade to documents). Every delete
   path that can remove documents must enqueue `storage_cleanup`. Mitigation: a DB trigger-free approach is fragile; instead, documents are
   deleted through one service function, and a nightly reconciliation task lists `storage_cleanup`-orphans (objects whose document row is
   gone). Workspace/subject/folder/chapter deletes must call that function first (M2 task, with tests per parent type).
2. **Rate limiter on Redis becomes a hard dependency of login.** Fail-closed would lock everyone out when Redis is down. See D-65 for the
   chosen behaviour.
3. **Quotas** (`AI_DAILY_TOKEN_QUOTA`) must count embedding tokens or document upload becomes an unmetered cost path (D-69).
4. **`BaseHTTPMiddleware` and large uploads:** the Phase 2 spike proved streaming responses, not streaming request bodies. M2 starts with a spike:
   stream a large multipart upload through the real middleware (CSRF, security headers, correlation id) with the size cap enforced, and
   convert to pure ASGI only if needed.
5. **Windows developer machines:** bind mounts and CRLF. Scripts used by containers must stay LF (`.gitattributes` already forces `eol=lf`).
