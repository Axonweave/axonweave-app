# Axonweave — Local Setup Guide

## Prerequisites

| Tool | Version |
|------|---------|
| Docker Desktop | ≥ 4.x |
| Docker Compose | ≥ 2.x (bundled with Docker Desktop) |
| Node.js | 22 LTS (for local frontend work only) |
| Python | 3.12 (for local backend work only) |

## Quick start

```bash
# 1. Clone the repository
git clone <repo-url>
cd axonweave-app

# 2. Create your .env file (never commit this)
cp .env.example .env
# Edit .env and set:
#   APP_SECRET_KEY — random 32+ char string
#   DATABASE_URL, DATABASE_MIGRATION_URL — already set for local dev
#   (leave SMTP settings as-is for Mailpit)

# 3. Start all services
docker compose up

# 4. Apply database migrations (first time only, or after schema changes)
docker compose exec backend alembic upgrade head

# 5. Open the app
open http://localhost:3000      # Frontend
open http://localhost:8025      # Mailpit (email UI for dev)
open http://localhost:8000/docs # Backend API docs
```

## Services

| Service | URL | Description |
|---------|-----|-------------|
| Frontend | http://localhost:3000 | Next.js app |
| Backend | http://localhost:8000 | FastAPI app |
| API docs | http://localhost:8000/docs | OpenAPI UI |
| Mailpit | http://localhost:8025 | Dev email inbox |
| PostgreSQL | localhost:5432 | Database |

## Running tests

```bash
# Backend tests (inside Docker)
docker compose exec backend pytest

# Backend tests (local Python)
cd backend && pytest

# Frontend unit tests
cd frontend && npm test

# E2E tests (requires full stack running)
cd frontend && npm run test:e2e
```

## Lint and type-check

```bash
# Backend
cd backend
ruff check .
ruff format --check .
mypy app

# Frontend
cd frontend
npm run lint
```

## Database migrations

```bash
# Apply all pending migrations
docker compose exec backend alembic upgrade head

# Check current state (must show exactly 1 head)
docker compose exec backend alembic heads

# Create a new migration after model changes
docker compose exec backend alembic revision --autogenerate -m "describe_change"
# Then review the generated file before committing
```

## Regenerate TypeScript API types

After any backend schema change:

```bash
cd backend && python scripts/export_openapi.py
cd frontend && npm run generate-types
```

## Troubleshooting

**Backend won't start — "missing env var"**  
Check your `.env` file has all variables from `.env.example`.

**Migration fails with "already exists"**  
The DB has a newer migration than your code. Run `git pull` to get the latest migrations.

**Email not arriving in tests**  
Check Mailpit at http://localhost:8025 — all outgoing email goes there in dev mode.

**Port conflict**  
Change `FRONTEND_PORT` / `BACKEND_PORT` in `.env` and update `docker-compose.yml` accordingly.
