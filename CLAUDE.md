# Axonweave — Claude Code project rules

Read this file at the start of every session. It is the standing contract for both developers.

## What we are building
Phase 1 "Application Foundation" of Axonweave: secure multi-user web app with auth, dashboard,
profile/settings, workspaces, subjects, folders, chapters. **No AI features in Phase 1.**

- Full requirements: `docs/PHASE1_SPEC.md` (source of truth — read the sections named in your task).
- Product context: `docs/Axonweave_PRD.docx` (background only).
- Decisions for things the spec leaves open: `docs/DECISIONS.md` (follow them; do not invent alternatives).
- Who owns what / task board: `docs/TASKS.md`.
- Git and parallel-work rules: `docs/WORKFLOW.md`.

## Stack (do not change without both developers agreeing)
Frontend: Next.js + React + TypeScript + Tailwind + shadcn/ui.
Backend: Python + FastAPI + SQLAlchemy + Alembic + Pydantic. DB: PostgreSQL. Passwords: Argon2id.
Sessions: opaque server-managed sessions in HTTP-only cookies (NOT JWT, NOT localStorage).
Tests: pytest (backend), Playwright (+ Vitest for components) (frontend). Docker Compose for local dev.
Modular monolith only: no microservices, no Kubernetes, no extra databases. Redis is NOT used in Phase 1.

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
- Frontend dev/test/lint: _(filled in by B0)_

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
12. Do not implement anything listed in spec section 23 (LLM, RAG, embeddings, PDF processing, flashcards, etc.). `backend/app/ai/` holds interfaces/placeholder only; the app must run with no LLM configured.
13. UTC timestamps in DB, IANA timezone strings, UUID primary keys, FK constraints, indexes, explicit delete/archive behaviour.
14. Every schema change = a new Alembic migration. **Never edit a migration that is merged to main.** Exactly one Alembic head on main.

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
- Stay inside your owned area (docs/TASKS.md). If you need a change in the other developer's area or a shared file, make the smallest possible change and say so in the PR description.
- Commit small and often with Conventional Commits (`feat(auth): ...`, `fix(workspaces): ...`, `test:`, `docs:`, `chore:`).
- Never push to `main`. Never force-push a shared branch. Never use `--no-verify`.
- If the spec is ambiguous or contradicts DECISIONS.md, stop and ask the developer instead of guessing.
- Report honestly: what was built, what was tested, what was not done.
