# Phase 1 acceptance (spec section 22)

Assessed 2026-11-04 on branch `chore/phase1-closeout`. Ratings:

- **Met**: implemented, and verified by an automated test or a check that was run (evidence named).
- **Partly**: something real exists and works, but part of the criterion is missing or unverified.
- **Not met**: not delivered.

"Local run" means the Docker Compose stack on the developer machine. **GitHub Actions has not been
observed running**, so no result below comes from CI.

## Overall

Phase 1 is **not complete**. The backend meets the criteria. The main gap is that the **subjects,
folders and chapters screens do not exist**: a user cannot create or manage them in the app, only
through the API. Several other items are partly met because the UI is covered only by tests that
mock the API, or because nothing was deployed. Tally: **Met 24, Partly 19, Not met 0** (43 items). Criteria that are "Partly" for lack of a UI are not "Met" just
because the API works.

## Authentication

| Criterion | Rating | Evidence / gap |
|---|---|---|
| User can register | Met | `test_auth.py::test_register_success`; `e2e/journey.spec.ts` registers through the UI and sees the check-your-email page |
| Duplicate email registration is prevented | Met | `test_auth.py::test_register_duplicate_email` (409) |
| Passwords are securely hashed | Met | `test_auth.py::test_registered_password_is_stored_as_argon2id_hash`; parameters in `docs/argon2-parameters.md` |
| Email verification works | Met | `test_email_auth.py`; `e2e/journey.spec.ts` reads the real email from Mailpit and follows the link ("Email verified") |
| User can log in | Met | `e2e/journey.spec.ts` (UI login on desktop and mobile) |
| User can log out | Met | `e2e/journey.spec.ts` logs out through the profile menu; back button then shows no protected data and the API answers 401 |
| Session expiration works | Met | `test_security_hardening.py::test_expired_session_rejected`. Backend only: how the UI behaves when a session expires mid-use is not tested |
| Password reset works | Partly | Backend: unknown, expired and reused tokens rejected, sessions revoked (`test_spec_security_cases.py::TestResetTokens`, `test_email_auth.py`). The forgot-password and reset-password pages have **no automated test** and were not exercised in a browser |
| Protected APIs reject unauthenticated requests | Met | `TestEveryProtectedEndpointRequiresAuth` calls every operation in the OpenAPI schema without a session; only six deliberately public routes are allowed |

## Dashboard

| Criterion | Rating | Evidence / gap |
|---|---|---|
| Dashboard displays real user information | Met | `e2e/dashboard-pages.spec.ts` (9 tests against the real API, no seeded data); `test_dashboard.py`, `test_dashboard_pages.py` |
| Sidebar navigation works | Partly | Links, active state, disabled "Coming soon" items and the mobile drawer are unit-tested (`sidebar-nav.test.tsx`). The **Subjects** link opens a placeholder page |
| Responsive layouts work | Partly | Checked: login and register at 375 px have no horizontal scroll (`journey.spec.ts`, both Playwright projects); the mobile drawer is unit-tested; the settings tabs were fixed to wrap. **Not checked:** other pages at phone or tablet widths, beyond the mobile project running the journey and settings specs |
| Loading and error states are implemented | Met | `AsyncSection` with loading, empty, error and retry used on dashboard, activity and archived pages (Task 1); workspaces and settings show toasts/errors |

## Profile and settings

| Criterion | Rating | Evidence / gap |
|---|---|---|
| User can view their profile | Partly | `test_users.py` for the API. The profile page (`settings/profile`) has no automated test |
| User can edit permitted profile details | Partly | Same: API tested, profile page UI not tested |
| User can change their password | Met | `e2e/settings.spec.ts`: change through the UI, old password then fails, new one works; backend `test_change_password_keeps_current_session_and_revokes_others` |
| User can manage sessions | Partly | List shows the current session in a real browser (`e2e/settings.spec.ts`); revoking another session is tested at API level and in the UI only with a mocked API |
| Account deletion workflow is defined and implemented | Met | D-23; backend tests; `e2e/settings.spec.ts` deletes an account through the UI and confirms login and `/auth/me` then fail. (The UI sent a wrong request body until this closeout; fixed) |

## Workspace

| Criterion | Rating | Evidence / gap |
|---|---|---|
| User can create a workspace | Met | `e2e/journey.spec.ts` creates one in the UI and finds it after reload |
| User can view their workspaces | Met | same spec; `test_workspaces.py::test_list_workspaces` |
| User can edit a workspace | Partly | Backend tested; the edit dialog was not exercised in a browser or unit test |
| User can archive and restore a workspace | Partly | Backend tested; `dashboard-pages.spec.ts` archives via the API and checks the archived page. The archive and restore **buttons** were not exercised |
| User can delete a workspace | Partly | Backend tested (`test_workspaces.py`, cross-user 404s); delete UI not exercised |

## Academic organisation

| Criterion | Rating | Evidence / gap |
|---|---|---|
| User can create subjects | Partly | **API only.** `test_subjects.py`; the journey creates one through the API. No UI exists |
| User can create folders | Partly | **API only.** `test_folders_chapters.py`. No UI |
| User can create chapters | Partly | **API only.** `test_folders_chapters.py`. No UI |
| User can edit and delete academic items | Partly | **API only** (`test_update_name`, `test_delete_success`, folder cascade tests, `test_delete_chapter`). No UI |
| Folder and chapter relationships are valid | Met | Backend: depth limit (`test_create_beyond_max_depth_rejected`), cross-user and wrong-parent 404s, delete-with-cascade rules, ownership joined up to the workspace |
| Search and sorting work | Partly | API: `test_search_by_name`, `test_sort_by_name_ascending_and_descending`, sort allowlist returns 422. No UI to use them |

## Data protection

| Criterion | Rating | Evidence / gap |
|---|---|---|
| User A cannot access User B's data | Met | Backend cross-user tests for workspaces, subjects, folders, chapters (`docs/SECURITY_REVIEW.md` section 1); `e2e/journey.spec.ts` second user gets 404 and sees nothing |
| All protected APIs enforce authorization | Partly | Authentication is swept over every route. Ownership is tested per resource type and key operations, **not swept over every route** with a second user |
| Database credentials are not exposed | Partly | Not in API responses or logs (tests; secret scan). But `docker-compose.yml` contains well-known **development** passwords as defaults, public if the repository is public |
| Secrets are not committed to Git | Met | `gitleaks` over full history: no leaks (one dummy test string ignored by fingerprint); only `.env.example` tracked |
| Sensitive information is excluded from logs | Met | Tests in `test_logging_and_db.py` and the auth tests; the console email sender no longer logs token links outside development. Production logs were not reviewed because there is no production |
| CSRF and rate limiting are implemented | Met | `TestCsrf`, `test_security.py`, `TestRateLimitIpSpoofing`. Limiter is in-process (single instance only, D-18) |
| HTTPS and secure cookies are configured for production | Partly | `COOKIE_SECURE` is forced on in production and tested. **HTTPS itself is not configured** and nothing has been deployed |
| Backup and restoration procedures are tested | Met | `docs/BACKUP_RESTORE.md`: real `pg_dump`/`pg_restore` on the dev database, counts, hashes, indexes and grants verified. Scope: local dev DB only; the app was not started against the restored DB |

## Code quality

| Criterion | Rating | Evidence / gap |
|---|---|---|
| Frontend and backend are separated | Met | `frontend/` and `backend/`, communicate only over `/api/v1`; types generated from OpenAPI |
| Backend follows modular architecture | Met | Route -> service -> repository -> model layout under `backend/app`; by inspection and review, not machine-enforced |
| Database migrations work | Partly | `alembic upgrade head` works and `alembic heads` shows one head (`0001`, a single initial migration). **Downgrade was not tested** |
| API documentation is available | Met | `/docs` and `/openapi.json` return 200 locally (development only by design) |
| Tests pass | Met | Local run: backend 234 tests (231 in the last full run plus 3 added after, which pass in their files), ruff and mypy clean; Vitest 93; Playwright 56 (CI-like config). **Not observed in CI** |
| Setup documentation is complete | Partly | `README.md`, `docs/SETUP.md`, `docs/DEPLOYMENT.md`, `docs/WORKFLOW.md` rewritten against the real repo. They were not followed from a clean clone, `.env.example` lacks `TRUST_PROXY_HEADERS`, and there is no production deployment recipe (`docs/DEPLOYMENT.md` lists what is missing) |

## Known problems that affect acceptance

1. **Subjects, folders and chapters UI missing** (dependent task: branch
   `feat/ui-subjects-folders-chapters`, planned but not started).
2. **Vulnerable Starlette** pulled in by the pinned FastAPI, and CI's `pip-audit` cannot see it
   (`docs/SECURITY_REVIEW.md` finding A).
3. **Production email is impossible** with the current SMTP sender (no TLS or authentication).
4. `npm run format:check` fails on files that predate this work; CI does not run it.
5. `docs/TASKS_Phase1.md` earlier recorded B4 "subjects backend + UI" and "Phase 1 complete" as done;
   the UI part was not delivered.
