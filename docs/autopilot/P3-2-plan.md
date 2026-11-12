# P3-2 plan
Finding: the upload and document-management API (Phase 3 M2) was already merged (27b16a7, later M3/M5/M7). This run audits it
against the P3-2 prompt, fills the one missing item and records the rest.

Gap found: item 4 (replace-file flow and version-switch transaction) has no API, no tests.
Plan:
1. `POST /documents/{id}/replace` (multipart, one file, same file type): same validation/quota/scan/streaming as upload,
   stores v(N+1), adds version row + queued job, bumps `latest_version`; `active_version` stays on the old version.
2. Version switch on completion (pipeline `_write`): activate new version and delete other versions' chunks in the same transaction.
3. Tests: replace keeps old active and searchable until completion; fake-completion switch; cross-user 404; unauthenticated sweep (existing OpenAPI walk).
4. Run ruff, mypy, full pytest; regenerate OpenAPI + frontend types.
