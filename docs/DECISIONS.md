# Decisions on points the spec leaves open

The spec (`PHASE1_SPEC.md`) is the source of truth. Where it is silent, incomplete or internally inconsistent, the defaults below apply
so that two developers and two Claude Code sessions do not invent different answers. Change a decision only by editing this file in a PR that both approve.

## Spec gaps found (schema is missing things the features need)

| ID | Gap | Decision |
|---|---|---|
| D-01 | Spec 7.1 asks for workspace "colour or icon", but table `workspaces` only has `icon`. | Add `colour` (VARCHAR, nullable) to `workspaces` in the initial migration. |
| D-02 | No table for email-verification tokens (spec 5.6) or pending email change (spec 6.2). | Add `email_verification_tokens` (same shape as `password_reset_tokens`, plus `purpose`: `verify_email` / `change_email`, and `new_email` nullable). Add `users.email_verified_at` (nullable timestamp) alongside `is_verified`. |
| D-03 | Users have no terms/consent record (spec 5.1 acknowledgement, 6.2 "manage consent"). | Add `users.terms_accepted_at` (timestamp) and `users.terms_version` (varchar). Registration is rejected without acknowledgement. |
| D-05 | Session list UI (spec 6.2) needs device info but `sessions` has none. | Add to `sessions`: `user_agent` (varchar, truncated), `ip_address` (inet or varchar), `revoked_at` (nullable), `remember_me` (bool). |
| D-06 | Theme and learning preferences (spec 6.2) have no storage. | Add table `user_preferences` (user_id unique FK, `theme` enum light/dark/system default system, `explanation_style`, `academic_level`, `study_preferences` JSONB). Reserved fields only; no logic. |
| D-07 | `users.status` values. | `pending_verification`, `active`, `suspended`, `deactivated`, plus `deletion_requested`. Use a CHECK constraint / enum. |
| D-08 | Activity log needs a readable description for the feed. | Add `activity_logs.entity_name` (varchar snapshot) and `workspace_id` (nullable FK, SET NULL) so the feed survives renames/deletes and can be filtered. Never store content beyond the name. |
| D-09 | Chapter `folder_id` must belong to the same subject (spec 12.3). | Enforce in the database with a composite FK `(folder_id, subject_id) -> folders(id, subject_id)` (add unique `(id, subject_id)` on folders) **and** in the service layer. |
| D-10 | `archived_at` exists on workspaces/subjects/folders/chapters but there is no `deleted_at`. | Delete = hard delete with explicit cascade rules (D-12). Archive = set `archived_at`. No soft-delete column in Phase 1 (spec 7.2 allows archive-then-delete). Add `deleted_at`-style soft deletion only if both developers agree. |
| D-11 | Unique names. | Unique (case-insensitive) per scope among non-archived rows: workspace name per user; subject name per workspace; folder name per parent; chapter title is not unique. Return 409 `CONFLICT`. |

## Behaviour decisions

| ID | Topic | Decision |
|---|---|---|
| D-04 | CSRF | Double-submit token: backend sets a non-HTTP-only `csrf_token` cookie; frontend echoes it in the `X-CSRF-Token` header on POST/PUT/PATCH/DELETE; backend compares with constant-time check **and** validates `Origin`/`Referer` against the allowlist. `SameSite=Lax`. |
| D-12 | Delete cascade | Deleting a workspace deletes its subjects, folders, chapters (DB `ON DELETE CASCADE`). Deleting a subject deletes its folders/chapters. Deleting a folder: **refused with 409 if it contains child folders or chapters**, unless `?cascade=true`, in which case contents are deleted. UI always shows a confirmation dialog stating what will be deleted. Archiving a parent hides children in lists but does not modify them. |
| D-13 | Default workspace | Registration creates a default workspace named "Personal" (type `personal_learning`). Exactly one default per user (partial unique index). The default workspace cannot be deleted until another is made default. |
| D-14 | Folder depth | Max depth 3 levels. Moves validated against self/descendant cycles and depth. |
| D-15 | Display order | Integer, gap-free per parent after reorder. `/chapters/reorder` accepts the full ordered id list for one subject/folder and runs in one transaction. |
| D-16 | Email verification policy | Unverified users can log in and use the academic features, see a persistent verification banner, and **cannot** change email, change password via settings, export data or request deletion until verified. |
| D-17 | Email delivery | Provider-agnostic `EmailSender` interface. Dev: Mailpit container in docker-compose (SMTP on 1025, UI on 8025). Console fallback. Real provider chosen later via `EMAIL_PROVIDER` env. Tests use an in-memory sender. |
| D-18 | Rate limiting | No Redis in Phase 1: use a small in-process limiter behind an interface (`RateLimiter`) so it can swap to Redis later. Limit per IP and per account/email for register, login, forgot-password, resend-verification, and resource creation. Return 429 with `Retry-After`. Document that multi-instance deployment needs the Redis backend. |
| D-19 | Session lifetime | Default session 7 days idle-sliding, absolute max 30 days; "remember me" extends idle to 30 days. Rotate session id on login and on password change. Changing password or resetting it revokes all other sessions. Cookie name `aw_session`, HTTP-only, `Secure` in production, `SameSite=Lax`, `Path=/`. |
| D-20 | Tokens | Session id, reset and verification tokens: 32 bytes from `secrets.token_urlsafe`, stored as SHA-256 hash. Reset token TTL 30 min; verification TTL 24 h; single use. |
| D-21 | Passwords | Min 12 chars, max 128. No composition rules. Check against a compromised-password list: use a local bundled list of the most common passwords (no external API call in Phase 1). Argon2id via `argon2-cffi`; benchmark parameters and record them in `docs/`. |
| D-22 | Re-authentication | Change password, change email, delete account, export data require the current password in the request (or a fresh login within 5 minutes). |
| D-23 | Account deletion | `DELETE /users/me` requires password + typed confirmation. Marks `deletion_requested`, revokes all sessions, then a deletion job (simple function invoked synchronously in Phase 1) deletes the user and all owned data (cascade), tokens, sessions, activity logs, and writes a content-free audit line (user id hash + timestamp). Settings UI explains exactly what is deleted before the final button. |
| D-24 | Data export | Add `GET /users/me/export` returning a JSON download of profile, preferences, workspaces, subjects, folders, chapters, activity. Requires re-auth (D-22). |
| D-25 | Security audit events | Structured JSON log on a dedicated `security` logger with correlation id, event type, user id (no PII beyond that), IP. Not stored in `activity_logs`. A DB audit table is a later option. |
| D-26 | Sidebar items | Real in Phase 1: Overview, My Workspace, Subjects, Recent activity, Archived items, Settings, Help and support (static help page), profile, logout. **Disabled "Coming soon"**: AI Tutor, Research Studio, Assessments, Revision, **Library**, **Favourites** (no storage in Phase 1 schema). |
| D-27 | Notifications icon | Visible placeholder with a disabled/“No notifications yet” popover. No fake notifications. |
| D-28 | Search/sort | Subjects: search by name, filter by workspace, sort by `name` or `updated_at`. Chapters: search by title within subject. Sort fields allowlisted. Case-insensitive `ILIKE` with escaped wildcards. |
| D-29 | Pagination | `limit` (default 20, max 100) and `offset`; list responses include `total`. |
| D-30 | Dashboard stats | Only counts computed from real rows scoped to the user. Empty states when zero. |
| D-31 | Security headers / CSP | Backend: `X-Content-Type-Options`, `Referrer-Policy`, `Cache-Control: no-store` on authenticated responses. Frontend (Next.js headers): CSP, `X-Frame-Options: DENY`/`frame-ancestors 'none'`, `Permissions-Policy`. HSTS in production. |
| D-32 | Row-Level Security | Not enabled in Phase 1 (application-level checks mandatory and tested). Evaluation of RLS is a documented follow-up in `docs/`. |
| D-33 | Database roles | Docker Compose creates an owner/migration role and a restricted application role without superuser. The app connects with the restricted role. |
| D-34 | Python/Node versions | Python 3.12, Node 22 LTS, PostgreSQL 16. Pin in Dockerfiles, `.python-version` / `.nvmrc`. Use `psycopg` v3 (matches `postgresql+psycopg://`). |
| D-35 | Language of UI | English only in Phase 1; `preferred_language` stored but not used for translation. |
| D-36 | Branding/UI | shadcn/ui default neutral theme, one accent colour, light/dark/system via CSS variables. Minimal, accessible, visible focus rings. |
