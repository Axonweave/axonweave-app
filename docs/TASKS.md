# Task board and ownership (Phase 1)

Spec step numbers refer to `PHASE1_SPEC.md` section 21. Tick a task only when its PR is merged to `main`.
**Dev A** = backend core, auth, security, users, infra. **Dev B** = app shell, academic structure, dashboard.

## Shared files (change minimally, mention in PR)
`backend/app/api/v1/router.py`, `backend/app/main.py`, `backend/app/models/__init__.py`, `docker-compose.yml`, `.env.example`, `frontend/package.json`, `README.md`.
Alembic: after any rebase run `alembic heads`; there must be exactly one head.

## Milestone 0 — Foundation (both start on day 1, in parallel, different folders)
- [x] **A0** (Step 1+2, backend half): repo skeleton, `backend/` FastAPI app per spec 17, config validation, structured logging with correlation id, Docker Compose (Postgres 16 + restricted app role + Mailpit + backend), SQLAlchemy base, **all tables from spec 12 + DECISIONS D-01..D-11 in one initial Alembic migration**, pytest setup with test DB, ruff/mypy, pre-commit, GitHub Actions CI (backend tests, lint, `alembic heads` check, frontend lint/build), `.env.example`, README, fill the Commands section in CLAUDE.md, `/health` endpoint, OpenAPI export script. ✅ merged 2026-11-02
- [ ] **B0** (Step 1, frontend half) — **Ashik**: `frontend/` Next.js + TS + Tailwind + shadcn/ui per spec 16, ESLint/Prettier, Vitest + Playwright config, design tokens + light/dark/system theme, centralised API client (credentials, CSRF header per D-04, error-envelope parsing), script generating TS types from backend OpenAPI, `frontend/Dockerfile`, security headers/CSP in `next.config`, reusable toast/confirm-dialog/empty/loading/error components.

## Milestone 1 — Sessions and shell
- [ ] **A1** (Step 3 part 1) — **Ashik**: password hashing (Argon2id), sessions table logic, `aw_session` cookie, CSRF (D-04), `get_current_user` / `require_active_user` / `require_verified_user` dependencies, `POST /auth/register` (creates profile, preferences, default "Personal" workspace in one transaction), `login`, `logout`, `GET /auth/me`, test fixtures `create_user_and_session`. **Merge this first; B2 depends on it.**
- [ ] **B1** (Step 4): app shell — sidebar (D-26), header (title, breadcrumbs, workspace selector, profile menu, notification placeholder), mobile drawer, collapsible sidebar, protected-route layout, no-cache on protected pages so back button after logout does not show data. Uses `/auth/me`.

## Milestone 2 — Parallel feature work
**Dev A**
- [ ] **A2** (Step 3 part 2 + security): rate limiting (D-18), CORS allowlist, security headers, security-event logging (D-25), brute-force delays, account status checks.
- [ ] **A3**: email verification + forgot/reset password + `EmailSender` (D-17), resend-verification, revoke sessions on reset.
- [ ] **A4** (spec 5 + 6): frontend auth pages (register, login, forgot, reset, verify-email) in the `(auth)` group.
- [ ] **A5** (spec 6 + 13.2): users API — profile get/patch, change password, change email with verification, sessions list/revoke, preferences, export (D-24), account deletion (D-23).
- [ ] **A6**: frontend profile + settings (account, appearance, learning prefs, privacy) — needs B1 merged.

**Dev B** (B2 starts once A1 is merged)
- [ ] **B2** (Step 5 backend): workspaces module + `activity` helper + tests.
- [ ] **B3** (Step 5 frontend): workspace list/create/edit/default/archive/restore/delete UI.
- [ ] **B4** (Step 6): subjects backend + UI (search, filter, sort, detail page).
- [ ] **B5** (Step 7): folders + chapters backend (move/reorder/validation, D-09, D-12, D-14, D-15) + UI (hierarchy, chapter detail with "coming soon" tabs).
- [ ] **B6** (Step 8): dashboard endpoints + UI, Recent activity page, Archived items page, Help page.

## Milestone 3 — Hardening (joint)
- [ ] **A7** (Step 9): security review led by A, reviewed by B: ownership tests for every endpoint, CSRF, rate limits, session tests, SQL injection tests, secrets scan, `pip-audit` / `npm audit`, log review.
- [ ] **B7** (Step 10): Playwright journey (register -> verify -> login -> workspace -> subject -> folder -> chapter -> refresh -> logout), responsive checks, empty/error states, API docs, setup/migration/deployment docs, backup & restore procedure test, tick spec section 22.
