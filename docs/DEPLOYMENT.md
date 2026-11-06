# Axonweave: deployment notes

> **Phase 1 has not been deployed anywhere.** This file records what the application needs and
> what is still missing; it is not a tested runbook. Target: a single server (Kubernetes and
> multiple instances are out of scope, and the in-process rate limiter requires one instance, D-18).

## What does not exist yet

- **No production Compose file or production images.** `docker-compose.yml` is a development setup
  (bind mounts, `uvicorn --reload`, dev database passwords, Mailpit). `backend/Dockerfile` is a dev
  image that includes test and lint tools. A production image should install `requirements.txt`
  only, run without `--reload` and as a non-root user.
- **No TLS / reverse proxy configuration.** HTTPS must be terminated in front of the app.
- **No production email.** The SMTP sender (`backend/app/core/email.py`) speaks plain SMTP with no
  STARTTLS and no authentication, so it works with Mailpit but not with typical hosted providers
  (port 587 or 465 with credentials). A provider-capable sender must be added before real users can
  receive verification or reset emails.
- **No scheduled backups, monitoring or log shipping.** See `docs/BACKUP_RESTORE.md` for the
  manual backup/restore procedure that was tested.
- **Dependencies:** the Starlette vulnerabilities are fixed on `fix/security-deps` (see section 5 of `docs/SECURITY_REVIEW.md`); six low/moderate `npm audit` advisories via `shadcn` remain.

## Configuration the backend reads (environment variables)

Set these through the host's secret management, never in a committed file.

| Variable | Notes |
|----------|-------|
| `APP_ENV` | `production` turns on the start-up guards below |
| `APP_SECRET_KEY` | at least 32 characters, random; must not be a placeholder |
| `DATABASE_URL` | restricted application role (`axonweave_app`), `postgresql+psycopg://...` |
| `DATABASE_MIGRATION_URL` | owner role (`axonweave_owner`), used for migrations only |
| `FRONTEND_URL`, `BACKEND_URL` | public URLs; `FRONTEND_URL` must be `https` in production. Also used for the CORS allowlist and email links |
| `COOKIE_SECURE` | must be `true` in production |
| `COOKIE_SAMESITE` | `lax` (default) |
| `EMAIL_PROVIDER` | `console` (default), `smtp` or in-memory for tests; see the email limitation above |
| `SMTP_HOST`, `SMTP_PORT` | used by the `smtp` provider |
| `EMAIL_FROM_ADDRESS`, `EMAIL_FROM_NAME` | sender identity |
| `TRUST_PROXY_HEADERS` | default `false`. Set `true` only if every request reaches the app through a proxy you control that overwrites `X-Forwarded-For`; otherwise clients can spoof their IP and weaken rate limits |

The frontend needs `NEXT_PUBLIC_BACKEND_URL` **at build time** (it is compiled into the bundle).

With `APP_ENV=production` the backend refuses to start if cookies are not secure, the secret is
a placeholder or the frontend URL is not https (tests in `backend/tests/test_closeout_users_config.py`).
It does not check the database passwords.

## Pre-deploy checklist

- [ ] Fresh random `APP_SECRET_KEY`; fresh database passwords (not the Compose defaults)
- [ ] `APP_ENV=production`, `COOKIE_SECURE=true`, https URLs
- [ ] Database roles exist (`infrastructure/docker/init-db.sql` shows the grants); consider removing
      write access to `alembic_version` from the app role (finding B in the security review)
- [ ] `alembic upgrade head` run with the owner role; `alembic heads` shows one head
- [ ] CI green on the commit; local backend, frontend and Playwright runs pass
- [ ] CI's dependency audit (installed `pip-audit` and `npm audit`) is green on the commit
- [ ] A backup was taken and a restore rehearsed on the target server

## Migrations

```bash
docker compose exec backend alembic upgrade head   # uses DATABASE_MIGRATION_URL
docker compose exec backend alembic heads          # exactly one head
```

## Rollback

1. Take a backup first (`docs/BACKUP_RESTORE.md`).
2. Deploy the previous commit.
3. If a migration must be undone: `alembic downgrade -1`. Downgrades were not rehearsed against
   real data; restoring the backup is the dependable path.

## Backup and restore

Use `docs/BACKUP_RESTORE.md` (custom-format `pg_dump`, `pg_restore`, verification steps). The old
plain-SQL `gzip | psql` instructions that used to be here were never run and have been removed.
