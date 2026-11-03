# Axonweave — Deployment Guide

> Phase 1 targets a single-server deployment. Kubernetes / multi-instance is out of scope.

## Environment variables (production)

Set these in your hosting platform's secret management (never in `.env` committed to git):

| Variable | Description |
|----------|-------------|
| `APP_ENV` | `production` |
| `APP_SECRET_KEY` | 32+ char random string (rotate if compromised) |
| `DATABASE_URL` | `postgresql+psycopg://axonweave_app:<pw>@host:5432/axonweave` |
| `DATABASE_MIGRATION_URL` | `postgresql+psycopg://axonweave_owner:<pw>@host:5432/axonweave` |
| `FRONTEND_URL` | Public frontend URL (e.g. `https://app.axonweave.com`) |
| `BACKEND_URL` | Public backend URL (e.g. `https://api.axonweave.com`) |
| `COOKIE_SECURE` | `true` |
| `COOKIE_SAMESITE` | `lax` |
| `EMAIL_PROVIDER` | `smtp` |
| `SMTP_HOST` | Your SMTP server |
| `SMTP_PORT` | `587` (TLS) or `465` (SSL) |
| `SMTP_USERNAME` | SMTP username |
| `SMTP_PASSWORD` | SMTP password |
| `SMTP_FROM_ADDRESS` | `noreply@yourdomain.com` |

## Pre-deploy checklist

- [ ] `APP_SECRET_KEY` is a fresh, random 32+ char string
- [ ] `COOKIE_SECURE=true`
- [ ] `APP_ENV=production`
- [ ] Run `alembic upgrade head` against the production DB
- [ ] `alembic heads` shows exactly one head
- [ ] All tests pass on the target commit
- [ ] `pip-audit` and `npm audit` show no high/critical CVEs

## Deploy steps

```bash
# 1. Pull latest code on the server
git pull origin main

# 2. Build and start with Docker Compose
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# 3. Run migrations
docker compose exec backend alembic upgrade head

# 4. Verify health
curl https://api.axonweave.com/health
```

## Database backup

```bash
# Backup
docker compose exec postgres pg_dump -U axonweave_owner axonweave | gzip > backup_$(date +%Y%m%d).sql.gz

# Restore
gunzip -c backup_20260101.sql.gz | docker compose exec -T postgres psql -U axonweave_owner axonweave
```

## Rollback

1. Identify the previous working commit: `git log --oneline`
2. Roll back the code: `git checkout <commit>`
3. If a migration was applied, downgrade: `alembic downgrade -1`
4. Rebuild and restart: `docker compose up -d --build`

## Security notes

- Never run the app as root inside Docker
- Use HTTPS only in production (`COOKIE_SECURE=true` enforces this)
- Rotate `APP_SECRET_KEY` if it is ever exposed — this invalidates all sessions
- Database owner role (`axonweave_owner`) is used only for migrations; app runs as `axonweave_app`
- Rate limiting is in-process in Phase 1; a single-server deployment is required (see D-18)
