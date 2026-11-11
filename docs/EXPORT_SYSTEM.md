# Export system (Phase 4)

Requirements: `PHASE4_SPEC.md` sections 14 and 19.5. Decision: D-100. Code: `app/study/exporting.py` (pure renderers), `app/study/export_runner.py` (worker), `app/modules/study/export_service.py` and `library_routes.py`; UI `frontend/src/features/study/export-menu.tsx`.

## Flow
1. `POST /study/materials/{id}/export` with `{ "format": "pdf" | "csv" | "md" | "docx" }` creates a `study_exports` row (`pending`) and queues a Celery task. 202. 503 `EXPORT_UNAVAILABLE` if there is no broker; 422 `EXPORT_FORMAT_UNSUPPORTED`; 429 `EXPORT_RATE_LIMITED` after 30 exports per user per hour.
2. The worker renders (PyMuPDF and python-docx live only in the worker image, D-70), writes the file to private object storage under `users/{user_id}/exports/{export_id}/file.{ext}` and marks it `completed` with `expires_at` (default one hour). Maximum file size 20 MB.
3. `GET /study/exports/{id}` returns status (`pending`, `completed`, `failed`, `expired`); `GET /study/exports/{id}/download` streams the file after an ownership check.
4. A sweeper resends undelivered exports and deletes expired files. Deleting a material, workspace or account queues its export files for storage cleanup.

## Formats
| Resource | Formats |
|---|---|
| Summary, study guide | PDF, DOCX, Markdown |
| Flashcards, glossary, question bank | CSV, PDF |
| Quiz, formula sheet | PDF |

## Safety
- Download is `attachment` with a fixed filename, `X-Content-Type-Options: nosniff`, `Cache-Control: no-store`; only the owner, only before expiry (410 `EXPORT_EXPIRED`); a foreign export is 404.
- CSV: any cell starting with `=`, `+`, `-`, `@`, tab, CR or LF (also after leading spaces) gets a leading apostrophe.
- PDF is drawn from plain text with a built-in Latin-1 font: no HTML or links are interpreted; characters outside Latin-1 show as `?` (known limit).
- Markdown escapes HTML and link syntax. DOCX strips control characters and writes text literally.
- Quiz and question-bank exports are built from the public view and NEVER include answer keys, explanations or rubrics, even after submission.
- Logs carry ids, format, size and status only.

## Tests
`backend/tests/study/test_library_export.py` (every type and format, injection payloads, hostile and non-Latin text, expired and foreign downloads, idempotent runs, rate limit, cleanup). PDF and DOCX cases skip in the API image (parsers are worker-only) and were checked by hand. `frontend/e2e/study.spec.ts` exports a deck to CSV through the real worker and downloads it.
