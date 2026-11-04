# Task board and ownership (Phase 1)

Spec step numbers refer to `PHASE1_SPEC.md` section 21. Tick a task only when its PR is merged to `main`.
**Dev A** = backend core, auth, security, users, infra. **Dev B** = app shell, academic structure, dashboard.

## Shared files (change minimally, mention in PR)
`backend/app/api/v1/router.py`, `backend/app/main.py`, `backend/app/models/__init__.py`, `docker-compose.yml`, `.env.example`, `frontend/package.json`, `README.md`.
Alembic: after any rebase run `alembic heads`; there must be exactly one head.

## Milestone 0 — Foundation (both start on day 1, in parallel, different folders)
- [x] **A0** (Step 1+2, backend half): repo skeleton, `backend/` FastAPI app per spec 17, config validation, structured logging with correlation id, Docker Compose (Postgres 16 + restricted app role + Mailpit + backend), SQLAlchemy base, **all tables from spec 12 + DECISIONS D-01..D-11 in one initial Alembic migration**, pytest setup with test DB, ruff/mypy, pre-commit, GitHub Actions CI (backend tests, lint, `alembic heads` check, frontend lint/build), `.env.example`, README, fill the Commands section in CLAUDE.md, `/health` endpoint, OpenAPI export script. ✅ merged 2026-11-02
- [x] **B0** (Step 1, frontend half) — **Ashik**: `frontend/` Next.js + TS + Tailwind + shadcn/ui per spec 16, ESLint/Prettier, Vitest + Playwright config, design tokens + light/dark/system theme, centralised API client (credentials, CSRF header per D-04, error-envelope parsing), script generating TS types from backend OpenAPI, `frontend/Dockerfile`, security headers/CSP in `next.config`, reusable toast/confirm-dialog/empty/loading/error components. ✅ merged 2026-11-03

## Milestone 1 — Sessions and shell
- [x] **A1** (Step 3 part 1) — **Ashik**: password hashing (Argon2id), sessions table logic, `aw_session` cookie, CSRF (D-04), `get_current_user` / `require_active_user` / `require_verified_user` dependencies, `POST /auth/register` (creates profile, preferences, default "Personal" workspace in one transaction), `login`, `logout`, `GET /auth/me`, test fixtures `create_user_and_session`. ✅ merged 2026-11-03
- [x] **B1** (Step 4): app shell — sidebar (D-26), header (title, breadcrumbs, workspace selector, profile menu, notification placeholder), mobile drawer, collapsible sidebar, protected-route layout, no-cache on protected pages so back button after logout does not show data. Uses `/auth/me`. ✅ merged 2026-11-03

## Milestone 2 — Parallel feature work
**Dev A**
- [x] **A2** (Step 3 part 2 + security): rate limiting (D-18), CORS allowlist, security headers, security-event logging (D-25), brute-force delays, account status checks. ✅ merged 2026-11-03
- [x] **A3**: email verification + forgot/reset password + `EmailSender` (D-17), resend-verification, revoke sessions on reset. ✅ merged 2026-11-03
- [x] **A4** (spec 5 + 6): frontend auth pages (register, login, forgot, reset, verify-email) in the `(auth)` group. ✅ merged 2026-11-03
- [x] **A5** (spec 6 + 13.2): users API — profile get/patch, change password, change email with verification, sessions list/revoke, preferences, export (D-24), account deletion (D-23). ✅ merged 2026-11-03
- [x] **A6**: frontend profile + settings (account, appearance, learning prefs, privacy). ✅ merged 2026-11-03

**Dev B** (B2 starts once A1 is merged)
- [x] **B2** (Step 5 backend): workspaces module + `activity` helper + tests. ✅ merged 2026-11-03
- [x] **B3** (Step 5 frontend): workspace list/create/edit/default/archive/restore/delete UI. ✅ merged 2026-11-03
- [x] **B4** (Step 6): subjects **backend** (search, filter, sort). ✅ merged 2026-11-03. *Correction 2026-11-04: the subjects UI (list, detail page) was never built; `/subjects` is a placeholder. Tracked in the closeout section below.*
- [x] **B5** (Step 7): folders + chapters backend (D-09, D-12, D-14, D-15). ✅ merged 2026-11-03
- [x] **B6** (Step 8): dashboard endpoints + UI, Recent activity page. ✅ merged 2026-11-03

## Milestone 3 — Hardening (joint)
- [x] **A7** (Step 9): security review — HTTPException format, CSRF/SQL-injection/session tests. ✅ merged 2026-11-03
- [x] **B7** (Step 10): Playwright auth + journey E2E specs, setup/deployment docs. ✅ merged 2026-11-03

## Phase 1 status
The board above records what was merged to `main` on 2026-11-03. It earlier said "Phase 1 complete";
**that was not accurate.** The honest status is in `docs/PHASE1_ACCEPTANCE.md` (24 of 43 section-22
criteria met, 19 partly met, none missing entirely). Work since then is on branch
`chore/phase1-closeout` and is **not merged**; tick items here only after that PR is merged.

## Phase 1b closeout (branch `chore/phase1-closeout`, 2026-11-04)
Ticked = done and verified in a local run. GitHub Actions has not been observed running.

- [x] Baseline run with coverage; backend 96 % line coverage (was under-reported at 75 % until coverage was told about greenlet).
- [x] Backend coverage gaps closed (`core/logging.py`, `database/connection.py` were below 80 %).
- [x] Spec 19.2: all 12 cases mapped to named tests in `docs/SECURITY_REVIEW.md`; cases 4 (all-routes 401 sweep) and 11/7/8/2/3 tests added.
- [x] Security fixes found while reviewing: forwarded-for spoofing, token links in logs, email HTML escaping, correlation-id injection, production config guards, change-email, data export, set-default race (list in the security review).
- [x] Vitest tests: auth schemas, API client, login and register pages, sidebar and mobile drawer, settings forms (93 tests).
- [x] Playwright: full journey (register -> Mailpit verification -> login -> workspace in UI -> subject/folder/chapter via API -> reload persistence -> logout -> back button), second-user isolation, mobile project, settings flows including account deletion. 56 tests pass locally with CI's configuration.
- [x] `auth.spec.ts` stale assertion fixed by fixing the product: registering now shows "Check your email" instead of bouncing to the login page.
- [x] CI workflow rewritten (backend, frontend, e2e, security jobs). **Written and replicated locally; not run on GitHub.**
- [x] `docs/BACKUP_RESTORE.md`: backup and restore actually run on the dev database and verified.
- [x] `docs/SECURITY_REVIEW.md`, `docs/PHASE1_ACCEPTANCE.md`, `docs/WORKFLOW.md`; README, SETUP and DEPLOYMENT rewritten to match the repo; spec section 22 checkboxes synced.
- [x] Backend dev image now includes test and lint tools, so the documented `docker compose exec backend pytest` works.

Not done (open):
- [ ] **Subjects / folders / chapters UI** (`feat/ui-subjects-folders-chapters`; plan exists, decisions on folder move and subject counts unanswered).
- [ ] Upgrade FastAPI/Starlette (seven advisories) and make CI audit transitive dependencies. Needs a team decision because it turns CI red until fixed.
- [ ] SMTP sender with STARTTLS and authentication; production images/compose file; TLS; scheduled backups.
- [ ] Restrict the app database role's access to `alembic_version`.
- [ ] Add `TRUST_PROXY_HEADERS=false` to `.env.example` (edit was blocked in the session; maintainer to do by hand).
- [ ] Browser tests for forgot/reset password, profile page, workspace edit/archive/restore/delete, session revoke.
- [ ] `npm run format:check` clean-up across the older frontend files.
- [ ] Merge `feat/ui-dashboard-pages` (the closeout branch includes its commits) and this branch; first CI run on GitHub.
