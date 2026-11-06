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
# Edit .env and set at least:
#   APP_SECRET_KEY — random string, 32+ characters
# The database URLs have working local defaults in docker-compose.yml.
# Leave the email settings as they are: mail goes to Mailpit in development.

# 3. Start all services (builds the images the first time)
docker compose up --build

# 4. Apply database migrations (first time only, or after schema changes)
docker compose exec backend alembic upgrade head
```

Then open http://localhost:3000 (app), http://localhost:8025 (Mailpit: verification and
password-reset emails arrive here) and http://localhost:8000/docs (API docs, development only).

The backend image is a development image: it includes pytest, ruff and mypy, so the commands
below work inside it. After changing `NEXT_PUBLIC_BACKEND_URL` or frontend dependencies rebuild
the frontend: `docker compose up -d --build frontend`.

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

# Frontend unit tests
cd frontend && npm test

# E2E tests (requires the full stack running; do not let Playwright start its own dev server)
cd frontend && PW_EXTERNAL_STACK=1 npx playwright test
# PowerShell: $env:PW_EXTERNAL_STACK='1'; npx playwright test
```

Registration and login are rate limited per IP (D-18). Repeated e2e runs can hit 429; restart the
backend (`docker compose restart backend`) to reset the in-process limiter. CI sets
`TRUST_PROXY_HEADERS=true` so tests can send distinct client IPs; leave it `false` locally and in
production unless you run behind your own proxy. The e2e specs read verification emails through
the Mailpit API at `http://localhost:8025/api/v1`.

The AI Tutor e2e tests (`e2e/ai-tutor.spec.ts`) need the **fake provider**, so they are deterministic,
free and never touch a real key. Start the stack with it, then run Playwright:

```bash
LLM_PROVIDER=fake LLM_DEFAULT_MODEL= FAKE_LLM_CHUNK_DELAY_SECONDS=0.1 TRUST_PROXY_HEADERS=true docker compose up -d --build
# PowerShell: $env:LLM_PROVIDER='fake'; $env:LLM_DEFAULT_MODEL=''; $env:FAKE_LLM_CHUNK_DELAY_SECONDS='0.1'; $env:TRUST_PROXY_HEADERS='true'; docker compose up -d --build
```

Variables set in your shell override `.env`, so your real Gemini key is not used. Unset them (or open a
new terminal) and run `docker compose up -d backend` to go back to the real provider. The fake provider
refuses to run when `APP_ENV=production` (D-60).

## Lint and type-check

```bash
# Backend
docker compose exec backend sh -c "ruff check . && ruff format --check ."
docker compose exec backend mypy app

# Frontend
cd frontend
npm run lint
npx tsc --noEmit
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

**Backend won't start with a validation error**  
`APP_SECRET_KEY` must be set (32+ characters). With `APP_ENV=production` the backend also refuses
to start on insecure cookie, URL or placeholder-secret settings.

**Migration fails with "already exists"**  
The DB has a newer migration than your code. Run `git pull` to get the latest migrations.

**Email not arriving in tests**  
Check Mailpit at http://localhost:8025 — all outgoing email goes there in dev mode.

**Port conflict**  
Ports are fixed in `docker-compose.yml` (3000, 8000, 8025, 1025, 5432). Stop whatever uses them or
edit the `ports:` mappings there.

**`pytest: executable file not found` in the backend container**  
The container was built before the Dockerfile installed `requirements-dev.txt`. Rebuild:
`docker compose up -d --build backend`.

**Registration or login returns 429 during repeated runs**  
That is the rate limiter working. Restart the backend to clear it.
