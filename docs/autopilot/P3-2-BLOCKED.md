# P3-2 - BLOCKED (cannot run the database-backed quality gates)

## Finding
The P3-2 scope (upload API, document APIs, delete lifecycle, export, security tests, OpenAPI) was **already merged to main**
(commits 27b16a7, 2b50aa0, c217298, a6d5b29). Audit against the prompt found one gap: item 4, the **replace-file flow and
version switch** had no API and no tests. This run built it.

## What was built (committed, NOT yet verified against a database)
- `POST /api/v1/documents/{id}/replace` (multipart, one file, same file type): same magic-byte / size / zip / image / scanner /
  quota checks as upload (shared `_validate_and_store`), stores `v(N+1)`, adds a version row and a queued job, bumps
  `latest_version`; `active_version` is untouched, so the old version stays active and searchable. 409 `PROCESSING_IN_PROGRESS`
  while the latest version is processing; 422 `FILE_TYPE_MISMATCH`; other users' documents are 404.
- `DocumentRepository.activate_version` now also deletes the other versions' chunks in the same transaction (version switch).
- `tests/documents/test_replace.py` (8 tests): old stays active, switch drops old chunks, download serves the active version,
  409 while processing, type mismatch, spoofed content, cross-user 404 with nothing stored, unauthenticated.
- OpenAPI regenerated and `frontend/src/types/api.generated.ts` updated (the existing 401 sweep walks OpenAPI, so it covers the new route).

## What blocked
This machine has no Docker engine (Docker Desktop is not installed/running) and no PostgreSQL/pgvector, so every DB-backed test
errors at setup (verified: an existing, unchanged upload test errors the same way). The gate "full pytest suite, migration
up/down" cannot be met, and shipping untested transaction code through an auto-merge pipeline is not safe.

Verified here: `ruff check`, `ruff format --check` (clean); `mypy app` shows only 2 pre-existing Windows-only errors
(`resource.setrlimit` in `app/ingestion/worker.py`); the new tests collect (8); OpenAPI export and type generation succeed.

## What a human must do
Run on a machine with Docker: `docker compose exec backend pytest tests/documents tests/ingestion tests/test_spec_security_cases.py`
then the full suite. If green, add the P3-2.md PR description (or re-run the pipeline there). No migration was added.
