# Axonweave — Claude Code project rules

Read this file at the start of every session. It is the standing contract for both developers.

## What we are building
Phase 1 "Application Foundation" (secure multi-user web app: auth, dashboard, profile/settings,
workspaces, subjects, folders, chapters) and **Phase 2 "AI Foundation"** (provider-independent AI layer, AI Tutor:
conversations, streaming, context, prompts, usage, quotas) are built. **Phase 3 "Document Intelligence and RAG"**
adds document upload, storage, extraction/OCR, chunking, embeddings, retrieval and source-cited answers. Nothing beyond that.

- Phase 1 requirements: `docs/PHASE1_SPEC.md` (source of truth for Phase 1).
- Phase 2 requirements: `docs/PHASE2_SPEC.md`; design: `docs/AI_ARCHITECTURE.md`; Phase 1 review and integration
  plan: `docs/AI_INTEGRATION_PLAN.md`; tasks: `docs/TASKS_Phase2.md`.
- Phase 3 requirements: `docs/PHASE3_SPEC.md`; design: `docs/DOCUMENT_ARCHITECTURE.md`; review of Phase 1/2 and conflicts:
  `docs/DOCUMENT_INTELLIGENCE_PLAN.md`; tasks: `docs/TASKS_Phase3.md`; decisions D-62 to D-76.
- Phase 4 "AI-Powered Study Generation" (summaries, flashcards, quizzes, guides, glossaries, formula sheets, question banks,
  library, versioning, export): `docs/PHASE4_SPEC.md`; design: `docs/STUDY_GENERATION_ARCHITECTURE.md`; tasks: `docs/TASKS_Phase4.md`;
  status: `docs/PHASE4_ACCEPTANCE.md`; security: `docs/GENERATION_SECURITY.md`; decisions D-78 to D-101. Quiz answer keys never leave
  the backend before submission; browser tests seed materials with `backend/scripts/seed_study_e2e.py`.
- Phase 6 "Learner Intelligence and Knowledge Graph" (concept extraction, PostgreSQL knowledge graph, learner evidence,
  explainable mastery, misconceptions, graph-aware recommendations): spec `docs/axonweave-phase6-7-specs/PHASE6_SPEC.md`;
  assessment: `docs/PHASE6_7_REPOSITORY_ASSESSMENT.md`; decisions D-122 to D-126. Code in `backend/app/knowledge/`. Phase 7
  (Research Studio, `docs/axonweave-phase6-7-specs/PHASE7_SPEC.md`, code in `backend/app/modules/research/`) is in progress, one milestone
  at a time (7.1 research projects, 7.2 paper library, 7.3 paper analysis, 7.4 comparison, 7.5 evidence matrix, 7.6 research gaps, 7.7 contradictions, 7.8 citations, 7.9 writing studio, 7.10 knowledge graph links, 7.11 dashboard, 7.12 testing done); Phase 7 acceptance: `docs/PHASE7_ACCEPTANCE.md`; Phase 6 acceptance: `docs/PHASE6_ACCEPTANCE.md`.
- Product context: `docs/Axonweave_PRD.docx` (background only).
- Decisions for things the spec leaves open: `docs/DECISIONS.md` (follow them; do not invent alternatives).
- Who owns what / task board: `docs/TASKS_Phase1.md`, `docs/TASKS_Phase2.md`.
- Git and parallel-work rules: `docs/WORKFLOW.md`.

## Stack (do not change without both developers agreeing)
Frontend: Next.js + React + TypeScript + Tailwind + shadcn/ui.
Backend: Python + FastAPI + SQLAlchemy + Alembic + Pydantic. DB: PostgreSQL. Passwords: Argon2id.
Sessions: opaque server-managed sessions in HTTP-only cookies (NOT JWT, NOT localStorage).
Tests: pytest (backend), Playwright (+ Vitest for components) (frontend). Docker Compose for local dev.
Modular monolith only: no microservices, no Kubernetes, no extra databases. Phase 3 adds (D-62, D-63): pgvector in the
same PostgreSQL, Redis (Celery broker and rate limiter), a Celery worker and beat (same codebase), S3-compatible object
storage. No separate vector database. Phase 1 and 2 features must keep working when these are not running.

## Repo layout
```
backend/   FastAPI app (app/api, core, database, models, schemas, repositories, services, modules, ai, tests), alembic/
frontend/  Next.js app (src/app, components, features, lib, hooks, types, styles)
infrastructure/  docker/compose helpers, CI scripts
docs/      spec, decisions, tasks, workflow, prompts
```
Backend layering is strict: **route -> service -> repository -> model**. Schemas (Pydantic) at the edges.
No business logic in route handlers. No SQL outside repositories.

## Commands
- Start everything: `docker compose up`
- Backend tests: `docker compose exec backend pytest` (or `cd backend && pytest` with local Python)
- Backend lint: `cd backend && ruff check . && ruff format --check .`
- Backend typecheck: `cd backend && mypy app`
- Migrations: `docker compose exec backend alembic upgrade head`
- Check migration state: `docker compose exec backend alembic heads` (must show exactly 1 head)
- Regenerate API types for frontend: `cd backend && python scripts/export_openapi.py`
- Frontend dev: `cd frontend && npm run dev`
- Frontend lint: `cd frontend && npm run lint`
- Frontend format: `cd frontend && npm run format:check`
- Frontend unit tests: `cd frontend && npm run test`
- Frontend e2e tests: `cd frontend && npm run test:e2e`
- Generate API types: `cd frontend && npm run generate-types`
- List models the configured key can use (names only, never the key; added in M1): `docker compose exec backend python scripts/list_llm_models.py`
- AI tests run on the fake provider and need no key: `docker compose exec backend pytest tests/ai`. Optional live-provider tests are marked `live` and skipped without a key.
- List embedding models the configured key can use (names only; added in Phase 3 M4): `docker compose exec backend python scripts/list_embedding_models.py`
- Run one `pytest` at a time (tests share one database).

## Non-negotiable rules
1. **Security is enforced in the backend.** Hiding UI is never authorization. Every protected endpoint:
   authenticated -> account active -> resource exists -> belongs to this user (including every parent in the chain) -> operation allowed.
2. **Non-owned resources return 404, not 403** (do not leak existence). UUIDs are not authorization.
3. Scope every query by owner (join up to `workspaces.user_id`). Never fetch by id alone and check later.
4. Validate all input on the backend with Pydantic. Allowlist sortable/filterable fields. Cap pagination limits.
5. Never concatenate user input into SQL. SQLAlchemy parameterised queries only.
6. Never log or return: passwords, password hashes, session ids/cookies, reset/verification tokens, API keys, stack traces, SQL, file paths.
7. Tokens (session, reset, verification) are stored **hashed**; raw values only ever go to the user.
8. Cookie-authenticated state-changing requests need CSRF protection (see DECISIONS D-04). CORS: explicit origin allowlist, no wildcard with credentials. CORS is not a CSRF defence.
9. Secrets only via environment variables. `.env` is gitignored; keep `.env.example` current with placeholder names only. Never read or print `.env`. If a secret is ever committed, tell the team to rotate it.
10. No hardcoded demo data, no fake statistics, no fake activity, no buttons that do nothing. Future modules are visibly "Coming soon" and disabled.
11. No TODO comments in place of security controls. If something can't be done, say so in the PR.
12. **AI (Phase 2).**
    - Provider API keys are backend-only environment variables held as `SecretStr`; never in the frontend, DB, logs or responses.
    - No provider SDK is imported outside `backend/app/ai/providers/` (a test enforces it). Adding a provider = one adapter file + one registry entry + model config.
    - LLM output is untrusted content: sanitise when rendering, never execute it, never trust model-generated ids.
    - Permissions are enforced in code, never by prompts. The LLM never decides access.
    - Never log message content, prompts or raw provider responses (ids, model, token counts, durations, error codes only).
    - `FakeProvider` is for tests and local UI development only and must refuse to run when `APP_ENV=production`.
    - Never hardcode model ids or prices from memory; verify them (D-38, D-39). Unknown cost is NULL, not 0.
    - The app must run with no provider configured (AI endpoints return 503 `LLM_NOT_CONFIGURED`).
    - Do not implement anything in Phase 2 spec section 24 that Phase 3 does not cover (flashcards, quizzes, audio, agents, tool execution). The knowledge graph is allowed from Phase 6 (D-122).
13. **Documents and RAG (Phase 3).**
    - Uploaded documents are untrusted input: validate magic bytes, enforce limits while streaming, never serve uploaded HTML, never execute or follow anything inside them.
    - Extraction, OCR and parsing run only in the Celery worker (never in the API process), with timeouts and memory limits.
    - Retrieval is always filtered by the authenticated user (via `ScopeResolver`) before any content reaches a model. No global vector search.
    - Never log document content, extracted text, queries, prompts or chunk text (ids, counts, scores, durations, error codes only).
    - Storage keys are generated by the backend, never from user input; the bucket is private; downloads are streamed after an ownership check (D-64).
    - Document text in prompts is untrusted data; model-generated citations are never trusted; the backend maps `[n]` markers to retrieved chunks only.
    - `FakeEmbeddingProvider` and the in-memory storage backend refuse `APP_ENV=production`. Never hardcode embedding model ids from memory (D-69).
    - No SDK for storage or embeddings outside its own package (`storage/s3_backend.py`, `embeddings/*_provider.py`); tests enforce it.
    - The app must run without Redis, worker, storage or embedder: only document endpoints answer 503.
    - Do not implement anything in Phase 3 spec section 24 (flashcard/quiz/study-guide generation, spaced repetition, adaptive learning, research analysis, audio/podcast, video). Knowledge graph work is Phase 6 (D-122 to D-126).
    - No copyrighted documents in git; fixtures are generated in code; real test files go in `testdata-private/` (ignored).
14. UTC timestamps in DB, IANA timezone strings, UUID primary keys, FK constraints, indexes, explicit delete/archive behaviour.
15. Every schema change = a new Alembic migration. **Never edit a migration that is merged to main.** Exactly one Alembic head on main.

## API conventions
- Base path `/api/v1`. REST. OpenAPI available at `/docs`.
- Success: `{"success": true, "data": ...}`  Error: `{"success": false, "error": {"code": "RESOURCE_NOT_FOUND", "message": "..."}}`
- Consistent status codes (400/401/403/404/409/422/429). 429 on rate limits. Pagination on list endpoints.
- The frontend TypeScript API types are **generated from the backend OpenAPI schema**, never hand-copied.

## Definition of done (per feature) — spec section 24
1 DB model -> 2 migration -> 3 schemas -> 4 repository+service -> 5 routes -> 6 auth+ownership checks ->
7 backend tests (incl. cross-user access denied) -> 8 UI -> 9 connect to API -> 10 frontend/e2e tests -> 11 verify workflow
and tick the matching acceptance criteria in spec section 22. Lint, typecheck and all tests must pass before opening a PR.

## Working agreement with Claude Code
- Start non-trivial tasks in **plan mode**. Present the plan; wait for approval.
- One task per session, one branch per task. Use `/clear` between tasks.
- Stay inside your owned area (docs/TASKS_Phase1.md). If you need a change in the other developer's area or a shared file, make the smallest possible change and say so in the PR description.
- Commit small and often with Conventional Commits (`feat(auth): ...`, `fix(workspaces): ...`, `test:`, `docs:`, `chore:`).
- Never push to `main`. Never force-push a shared branch. Never use `--no-verify`.
- If the spec is ambiguous or contradicts DECISIONS.md, stop and ask the developer instead of guessing.
- Report honestly: what was built, what was tested, what was not done.
