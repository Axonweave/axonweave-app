# P4-1 plan - Summary generator (backend only)
- `summary` generator: six types, settings (spec 5.3), structured output of sections (5.4), refs stripped like citations.
- Engine: optional ordered map-reduce (map per batch -> condense -> reduce), coverage report (documents, chunks, batches), min-source check.
- Migration 0005: `generation_jobs.preview` (JSONB) for regenerate previews.
- API: PATCH /study/materials/{id} (edit, optimistic version), GET versions, POST regenerate (whole or section) -> job with preview, GET preview, POST apply (new version, never overwrites; stale preview = 409).
- Tests: each type, attribution, coverage, thin source, injection, edit, regenerate, ownership.
