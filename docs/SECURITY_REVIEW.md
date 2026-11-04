# Phase 1 security review

Date: 2026-11-04. Branch `chore/phase1-closeout`. Reviewer: the developer working with Claude Code.
This is a self-review of the code in this repository plus automated checks. It is **not** an
independent penetration test, and nothing here was run against a deployed environment.

## 1. Spec 19.2 essential cases, mapped to tests

Backend tests run in the `backend` container (full suite: **231 passed**, see section 3). Test files live
in `backend/tests/`.

| # | Case | Test(s) |
|---|------|---------|
| 1 | User A cannot access User B's workspace | `test_workspaces.py::test_cross_user_workspace_access_denied`; `test_subjects.py::test_cross_user_workspace_404`; `test_closeout_users_config.py::...::test_restore_of_other_users_workspace_is_404` (restore, delete and patch all 404) |
| 2 | User A cannot edit User B's subject | `test_spec_security_cases.py::TestCrossUserMutations::test_user_cannot_edit_other_users_subject` (also archive/restore/delete: `...::test_user_cannot_archive_restore_or_delete_other_users_subject`) |
| 3 | User A cannot delete User B's chapter | `TestCrossUserMutations::test_user_cannot_delete_other_users_chapter`; `test_folders_chapters.py::test_cross_user_chapter_404`, `::test_cross_user_folder_404` |
| 4 | Unauthenticated user cannot access protected endpoints | `TestEveryProtectedEndpointRequiresAuth`: every operation under `/api/v1` in the OpenAPI schema is called without a session and must return 401. Public routes are an explicit allowlist (register, login, verify-email, forgot-password, reset-password, logout). Also `test_auth.py::test_me_unauthenticated`, `test_workspaces.py::test_workspaces_requires_auth` |
| 5 | Expired session cannot access protected resources | `test_security_hardening.py::test_expired_session_rejected` |
| 6 | Revoked session cannot be reused | `test_security_hardening.py::test_revoked_session_rejected`; `test_auth.py::test_session_invalidated_after_logout`; `TestResetTokens::test_reset_revokes_existing_sessions` |
| 7 | Invalid password-reset tokens rejected | `TestResetTokens::test_unknown_reset_token_rejected`; `test_email_auth.py::test_reset_password_expired_token` |
| 8 | Password-reset token cannot be reused | `TestResetTokens::test_reset_token_cannot_be_reused` |
| 9 | Invalid input rejected | `test_security_hardening.py`: `test_oversized_email_rejected`, `test_oversized_name_in_register`, `test_invalid_uuid_in_path`, `test_weak_passwords_rejected`, `test_error_format_422`; `test_subjects.py::test_invalid_colour`; `test_preferences_roundtrip_and_invalid_theme_rejected` |
| 10 | SQL injection does not alter queries | `test_security_hardening.py::test_sql_injection_in_email_login`, `::test_sql_injection_in_register_name`. **Limit:** two injection points are tested. The rest rely on SQLAlchemy parameterised queries and a repository-only SQL rule (CLAUDE.md rule 5) that was not machine-checked beyond review |
| 11 | Cross-origin requests cannot bypass CSRF | `TestCsrf`: cross-origin request with a valid token rejected, missing token header rejected, mismatched token rejected, CORS does not allow a foreign origin; `test_security_hardening.py::test_logout_without_csrf_rejected`, `::test_logout_with_wrong_csrf_rejected` |
| 12 | Rate limits enforced | `test_security.py::test_register_rate_limit`, `::test_login_rate_limit`; `test_export_is_rate_limited`; `TestRateLimitIpSpoofing` |

## 2. Defects found during the closeout and fixed

1. **Rate-limit bypass:** `X-Forwarded-For` was trusted unconditionally, so any client could dodge
   per-IP limits by sending a fake header. It is now honoured only when
   `TRUST_PROXY_HEADERS=true`. Test: `TestRateLimitIpSpoofing`.
2. **Tokens in logs:** the console email sender logged full message bodies, including
   verification and reset links, in every environment. Bodies are now logged only when
   `APP_ENV=development`; otherwise only a masked recipient and the subject.
3. **HTML injection in emails:** name and URL were interpolated unescaped into HTML. Now escaped.
4. **Log injection:** a client-supplied correlation id was echoed into logs and responses. It is now
   accepted only if it matches `[A-Za-z0-9._-]{1,64}`.
5. **Weak production guards:** production start-up now refuses placeholder or short secrets,
   insecure cookies and other unsafe settings (`core/config.py`; tests in
   `test_closeout_users_config.py`).
6. **Change-email was a stub** and **data export was minimal**: both implemented properly with
   owner-scoped queries (`export_repository.py`) and the email verification flow.
7. **Account deletion from the UI sent the wrong request body** (so the feature could not work);
   the settings page now sends `password` and the `delete my account` confirmation the API expects.
   Covered by a unit test and by `e2e/settings.spec.ts`, which deletes an account through the UI and
   checks that login and `/auth/me` then fail.
8. **Registration redirect:** the register page pushed to `/dashboard`, but registration opens no
   session, so users were silently bounced to the login page with no message. It now tells the user
   to check their email.
9. **Intermittent unique-index violation** when changing the default workspace (race in clearing the
   old default). Fixed by flushing the clear before setting the new default.

## 3. Checks run (2026-11-04)

| Check | Result |
|-------|--------|
| Backend tests, `pytest --cov=app` in the container | **231 passed**, **96 %** line coverage (2598 statements, 115 missed), includes the 49-case all-routes sweep |
| `ruff check` / `ruff format --check` | pass |
| `mypy app` | pass (76 files) |
| `alembic heads` | exactly one head (`0001`) |
| Frontend Vitest | 93 passed (10 files) |
| Frontend `tsc --noEmit`, `npm run lint` | pass |
| Playwright, whole suite (auth, journey, settings, dashboard-pages) on chromium and Mobile Chrome | **56 passed**, run against the Docker stack with `TRUST_PROXY_HEADERS=true` as CI configures it. With it `false` (the local default) the 10-registrations-per-15-minutes limit is hit by a full two-project run and registration specs fail with "Too many requests" |
| `gitleaks detect` (full git history, 36 commits at the time) | no leaks. One finding (a dummy test password in an old commit) is ignored by exact fingerprint in `.gitleaksignore`; a CI-only throwaway key is allowlisted in `.gitleaks.toml` |
| `npm audit --omit=dev --audit-level=high` | exit 0; 6 low/moderate advisories, none high or critical |
| `pip-audit -r requirements.txt --no-deps` (what CI runs) | "No known vulnerabilities found", **but see finding A: this check cannot see transitive dependencies** |
| Log review | tests in `test_logging_and_db.py` and the auth tests assert that responses and logs omit passwords, hashes, session ids and tokens; the console sender change above closed the known leak. This is test-based plus code reading, not a review of production logs |
| Production config refuses to start when unsafe | tested (`test_closeout_users_config.py`) |
| Secrets in git | only `.env.example` (placeholders) is tracked; `.env` is untracked and was never read |

## 4. Open findings (not fixed)

**A. Vulnerable Starlette (high priority follow-up).** `fastapi==0.115.5` pulls in
`starlette==0.41.3`. `pip-audit` on the installed environment lists seven distinct advisories
against it: PYSEC-2026-1941 (multipart spool, fix 0.47.2), -1942 (Range header, 0.49.1), -161 (Host
header, 1.0.1), -248 (request path, 1.3.0), -249 (form limits, 1.3.1), -2280 and -2281
(`HTTPEndpoint` method dispatch and Windows `StaticFiles`, 1.1.0). The app does not parse forms,
serve static files or use `HTTPEndpoint`, which likely limits exposure to some of them, but the
Host-header, path and Range advisories were **not** assessed for this app. Fixing it needs a
FastAPI upgrade, which is a larger change than a closeout should make unreviewed. The CI step
`pip-audit -r requirements.txt --no-deps` reports clean because Starlette is not listed in
`requirements.txt`; the gate gives false assurance until the transitive dependencies are pinned or
audited. Changing it would turn CI red today, so that decision is left to the team.
`pip` 25.0.1 and `pytest` 8.3.4 in the dev image also have advisories (dev tooling only).

**B. The app database role can modify migration state.** `init-db.sql` grants `SELECT, INSERT,
UPDATE, DELETE` on all current and future tables, which includes `alembic_version`. Decision D-33
only requires a non-superuser, so this is within the decision, but least privilege would exclude it.

**C. Dev credentials are defaults in `docker-compose.yml`.** The database passwords there are
well-known dev values used when no `.env` is present. They must never reach a shared or production
environment; production start-up checks cover `APP_SECRET_KEY` and cookie settings, not the
database passwords in the URL.

**D. HTTPS is not configured anywhere in this repository.** `COOKIE_SECURE` and the production
guards exist, but TLS termination is a deployment task and no deployment has been done or tested.

**E. Rate limiting is in-process (D-18).** It resets on restart and does not work across multiple
instances. Acceptable for the single-server Phase 1 target; wrong for anything scaled out.

**F. `.env.example` does not list `TRUST_PROXY_HEADERS`.** Edits to that file were blocked in this
session, so the maintainer must add `TRUST_PROXY_HEADERS=false` (default, safe) by hand. CI sets
it to `true` for the e2e job only.

**G. Email cannot be sent through a real provider.** `SmtpEmailSender` uses plain SMTP with no
STARTTLS or authentication. Not a vulnerability, but verification and reset emails cannot be
delivered in production until this is fixed (see `docs/DEPLOYMENT.md`).

**H. Repository visibility.** If the code is meant to be private, confirm the GitHub repository is
private. The repository history was scanned for secrets and none were found, but the dev default
passwords in `docker-compose.yml` are public if the repo is.

**I. Not tested:** the change-email flow end to end in a browser; forgot/reset password pages in a browser; behaviour behind
a real reverse proxy; load or abuse beyond the per-endpoint limits; dependency licences.
