# Axonweave

Personal academic workspace. **Phase 1 "Application Foundation"**: a secure multi-user web app with
authentication, a dashboard, profile and settings, workspaces, and a subjects / folders / chapters
data model. **Phase 2 "AI Foundation"** adds a provider-independent AI layer and the **AI Tutor**
(streaming chat with saved conversations, usage tracking and quotas). The app still runs with no
LLM configured: the AI endpoints answer 503 and the AI Tutor says AI is not configured.

> **Status.** The backend is complete for Phase 1. The frontend covers authentication, dashboard,
> recent activity, archived items, workspaces, settings and help. The **subjects, folders and
> chapters screens are not built yet** (the `/subjects` page is a placeholder); those entities are
> available through the API only. See `docs/PHASE1_ACCEPTANCE.md` for a line-by-line account of
> what is and is not met. Phase 2 (AI) status, item by item: `docs/PHASE2_ACCEPTANCE.md`.

## Stack

Next.js 16 + React 19 + TypeScript + Tailwind + shadcn/ui (frontend); Python 3.12 + FastAPI +
SQLAlchemy + Alembic + Pydantic (backend); PostgreSQL 16; Argon2id password hashing; opaque
server-side sessions in HTTP-only cookies with CSRF protection. Docker Compose for local
development. Modular monolith; Redis is used from Phase 3 (Celery, rate limiter); no microservices.

## AI Tutor (Phase 2)

Open **AI Tutor** in the sidebar. It needs a provider; without one the page shows a clear "AI is not
configured" state. To connect Gemini, put `LLM_PROVIDER=gemini` and `GEMINI_API_KEY` in your local
`.env`, list the models your key can use with
`docker compose exec backend python scripts/list_llm_models.py`, set `LLM_DEFAULT_MODEL` to one of them
and restart the backend (`docker compose up -d backend`). Details, limits and adding another provider
(for example Qwen or Llama): `docs/LLM_PROVIDER_INTEGRATION.md`. The first time a user opens the
tutor they see a notice that conversations are sent to the configured provider.

For UI work without a key, `LLM_PROVIDER=fake` runs a deterministic test provider (development and
testing only; the tutor shows a "Test provider, not a real AI" badge). **Never commit a key.**

## Prerequisites

- Docker Desktop (with Docker Compose)
- Git
- Node.js 22 and Python 3.12 only if you run the frontend or backend outside Docker

## Quick start

```bash
git clone <repo-url>
cd axonweave-app
cp .env.example .env        # then replace the placeholder values (never commit .env)
docker compose up --build
docker compose exec backend alembic upgrade head
```

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000/api/v1 |
| API docs (development only) | http://localhost:8000/docs |
| Health check | http://localhost:8000/health |
| Mailpit (development inbox; verification and reset emails land here) | http://localhost:8025 |
| PostgreSQL | localhost:5432 |

The frontend image bakes in the backend URL at build time (`NEXT_PUBLIC_BACKEND_URL`), so rebuild
it (`docker compose up --build frontend`) if you change that value.

Full setup notes and troubleshooting: `docs/SETUP.md`.

## Commands

```bash
# Backend (the backend image is a development image and includes the test and lint tools)
docker compose exec backend pytest -m "not live"   # live tests call the real provider; skip them
docker compose exec backend sh -c "ruff check . && ruff format --check ."
docker compose exec backend mypy app
docker compose exec backend alembic heads          # must print exactly one head

# Frontend
cd frontend
npm run lint
npm run test               # Vitest unit/component tests
npm run test:e2e           # Playwright; needs the full stack running (see below)

# API types: export the OpenAPI schema, then generate the frontend types
cd backend && python scripts/export_openapi.py
cd frontend && npm run generate-types
```

Playwright against the Docker stack that is already running:

```bash
cd frontend
PW_EXTERNAL_STACK=1 npx playwright test          # PowerShell: $env:PW_EXTERNAL_STACK='1'; npx playwright test
```

Registration and login are rate limited per IP, so the end-to-end specs share sessions where they
can. CI sets `TRUST_PROXY_HEADERS=true` so each test registration can present a distinct client IP;
do not set that in production unless the app is behind a proxy you control.

The AI Tutor specs (`e2e/ai-tutor.spec.ts`) need the stack to run with the fake provider
(`LLM_PROVIDER=fake`, optionally `FAKE_LLM_CHUNK_DELAY_SECONDS=0.1`); CI does this. See `docs/SETUP.md`
and `docs/AI_TESTING.md`.

`npm run format:check` currently reports formatting drift in files that predate the Phase 1
closeout; CI does not run it.

## Continuous integration

`.github/workflows/ci.yml` has four jobs: backend (ruff, mypy, migrations, `alembic heads`, pytest),
frontend (lint, typecheck, Vitest, build), e2e (Playwright against the Compose stack, using
Mailpit for email verification, with the fake AI provider) and security (gitleaks on history,
`pip-audit`, `npm audit`). The workflow runs on every pull request; the three most recent runs on `main`
(including the AI Tutor merge, PR #15) were green when checked on 2026-11-06.

## Repository layout

```
backend/          FastAPI app: api, core, database, models, repositories, services, modules, ai (provider layer, orchestration), tests; alembic/
frontend/         Next.js app: src/app, components, features, lib, hooks, types; e2e/ (Playwright)
infrastructure/   Docker init scripts for the database roles and the test database
docs/             Spec, decisions, task board, workflow, setup, deployment, backup, security review, acceptance
```

Backend layering is strict: **route -> service -> repository -> model**; no business logic in route
handlers and no SQL outside repositories.

## Security summary

- Passwords: Argon2id. Sessions, reset and verification tokens are stored hashed.
- Authorization is enforced in the backend; resources owned by other users answer 404.
- CSRF double-submit token plus Origin check on state-changing cookie requests; explicit CORS allowlist.
- Per-IP rate limits (in-process, single instance).
- Production start-up refuses unsafe configuration.
- Review, test mapping and the **findings and the dependency audit:
  `docs/SECURITY_REVIEW.md`. AI-specific review: `docs/AI_SECURITY.md`.
- AI: the provider key is a backend-only environment variable; no message content is logged; model output
  is rendered as sanitised Markdown and never trusted for access decisions; per-user rate limits and daily
  quotas apply.

## Documentation

| File | Purpose |
|---|---|
| `docs/PHASE1_SPEC.md` | Requirements (source of truth) |
| `docs/DECISIONS.md` | Decisions for things the spec leaves open |
| `docs/TASKS_Phase1.md` | Task board and the Phase 1b closeout |
| `docs/PHASE1_ACCEPTANCE.md` | Spec section 22, item by item, with evidence |
| `docs/PHASE2_SPEC.md`, `docs/TASKS_Phase2.md` | Phase 2 requirements and task board |
| `docs/PHASE2_ACCEPTANCE.md` | Phase 2 spec section 23, item by item, with evidence |
| `docs/AI_ARCHITECTURE.md` | AI design: providers, orchestration, context, streaming, data model |
| `docs/LLM_PROVIDER_INTEGRATION.md` | Configuring a provider; adding Qwen or Llama |
| `docs/AI_API_REFERENCE.md`, `docs/CONVERSATION_MANAGEMENT.md`, `docs/USAGE_AND_COST_TRACKING.md` | API, conversations and context, usage and quotas |
| `docs/AI_SECURITY.md`, `docs/AI_TESTING.md`, `docs/AI_EVALUATION.md` | AI security review, how to run the tests, answer-quality evaluation |
| `docs/WORKFLOW.md` | Branching, commits, pull requests |
| `docs/SETUP.md`, `docs/DEPLOYMENT.md` | Running locally; what a deployment still needs |
| `docs/BACKUP_RESTORE.md` | Backup and restore procedure that was run and checked |
| `docs/SECURITY_REVIEW.md` | Security review and open findings |
| `CLAUDE.md` | Working agreement for Claude Code |

If this repository is meant to be private, make sure the GitHub repository visibility is set to
private; the Compose file contains well-known development database passwords.
