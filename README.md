# Axonweave

Personal academic workspace. **Phase 1 "Application Foundation"**: a secure multi-user web app with
authentication, a dashboard, profile and settings, workspaces, and a subjects / folders / chapters
data model. There are **no AI features in Phase 1** and the app runs with no LLM configured.

> **Status.** The backend is complete for Phase 1. The frontend covers authentication, dashboard,
> recent activity, archived items, workspaces, settings and help. The **subjects, folders and
> chapters screens are not built yet** (the `/subjects` page is a placeholder); those entities are
> available through the API only. See `docs/PHASE1_ACCEPTANCE.md` for a line-by-line account of
> what is and is not met.

## Stack

Next.js 16 + React 19 + TypeScript + Tailwind + shadcn/ui (frontend); Python 3.12 + FastAPI +
SQLAlchemy + Alembic + Pydantic (backend); PostgreSQL 16; Argon2id password hashing; opaque
server-side sessions in HTTP-only cookies with CSRF protection. Docker Compose for local
development. Modular monolith; no Redis, no microservices.

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
docker compose exec backend pytest
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

`npm run format:check` currently reports formatting drift in files that predate the Phase 1
closeout; CI does not run it.

## Continuous integration

`.github/workflows/ci.yml` has four jobs: backend (ruff, mypy, migrations, `alembic heads`, pytest),
frontend (lint, typecheck, Vitest, build), e2e (Playwright against the Compose stack, using
Mailpit for email verification) and security (gitleaks on history, `pip-audit`, `npm audit`). The
workflow has been written and its steps replicated locally, but it has not been observed running on
GitHub.

## Repository layout

```
backend/          FastAPI app: api, core, database, models, repositories, services, modules, ai (placeholder), tests; alembic/
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
- Review, test mapping and the **open findings** (including vulnerable transitive dependencies):
  `docs/SECURITY_REVIEW.md`.

## Documentation

| File | Purpose |
|---|---|
| `docs/PHASE1_SPEC.md` | Requirements (source of truth) |
| `docs/DECISIONS.md` | Decisions for things the spec leaves open |
| `docs/TASKS_Phase1.md` | Task board and the Phase 1b closeout |
| `docs/PHASE1_ACCEPTANCE.md` | Spec section 22, item by item, with evidence |
| `docs/WORKFLOW.md` | Branching, commits, pull requests |
| `docs/SETUP.md`, `docs/DEPLOYMENT.md` | Running locally; what a deployment still needs |
| `docs/BACKUP_RESTORE.md` | Backup and restore procedure that was run and checked |
| `docs/SECURITY_REVIEW.md` | Security review and open findings |
| `CLAUDE.md` | Working agreement for Claude Code |

If this repository is meant to be private, make sure the GitHub repository visibility is set to
private; the Compose file contains well-known development database passwords.
