# Axonweave

Personal academic intelligence workspace — Phase 1 foundation.

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (includes Docker Compose)
- Git

## Quick start

```bash
# 1. Clone and enter the repo
git clone <repo-url>
cd axonweave-app

# 2. Create your local environment file
cp .env.example .env
# Edit .env — replace all placeholder values with real secrets

# 3. Start all services (Postgres, Mailpit, backend)
docker compose up
```

Services after startup:

| Service | URL |
|---|---|
| Backend API | http://localhost:8000 |
| API docs (dev only) | http://localhost:8000/docs |
| Health check | http://localhost:8000/health |
| Mailpit (dev email) | http://localhost:8025 |
| Postgres | localhost:5432 |

## Commands

### Run database migrations

```bash
docker compose exec backend alembic upgrade head
```

### Run backend tests

```bash
docker compose exec backend pytest
# Or locally (requires a running Postgres):
cd backend && pytest
```

### Backend lint, format, type-check

```bash
cd backend
ruff check .
ruff format --check .
mypy app
```

### Export OpenAPI schema (for frontend type generation)

```bash
cd backend && python scripts/export_openapi.py
# Writes backend/openapi.json
```

### Check Alembic migration state

```bash
docker compose exec backend alembic heads   # must show exactly 1 head
docker compose exec backend alembic history
```

## Architecture

```
axonweave-app/
├── backend/       FastAPI app — api, core, database, models, schemas, services, modules
├── frontend/      Next.js app (added in task B0)
├── infrastructure/  Docker init scripts
├── docs/          Spec, decisions, task board, workflow
├── docker-compose.yml
└── .env.example
```

Backend layer order: **route → service → repository → model**. No business logic in routes; no SQL outside repositories.

## Security notes

- Passwords hashed with Argon2id.
- Sessions are server-managed opaque tokens stored as SHA-256 hashes.
- All secrets via environment variables; `.env` is gitignored.
- See `docs/PHASE1_SPEC.md` section 14 for the full security specification.

## Development

See `docs/WORKFLOW.md` for branch and PR conventions.
See `docs/TASKS.md` for the task board.
See `CLAUDE.md` for the working agreement with Claude Code.
