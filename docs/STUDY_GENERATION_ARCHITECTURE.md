# Study generation architecture (Phase 4, M0)

Design of the common generation engine. Requirements: `PHASE4_SPEC.md` sections 3, 4, 17, 18.1 to 18.3, 21. Decisions: D-78 to D-90.
Rule of the phase: generators are thin; everything shared lives in the engine. Nothing from Phase 3 is rebuilt.

## 1. Review of Phase 1 to 3: what is reused

| Need | Reused from | How |
|---|---|---|
| Documents, versions, processing status | `documents`, `document_versions` (Phase 3) | Only documents that are `completed` with an active version are readable. |
| Chunks and provenance | `document_chunks` (page, slide, section, ids) | Read with owner-scoped queries (`StudySourceRepository`); provenance is stored as ids, never text. |
| Access control | `ScopeResolver` (one new method: `resolve_documents` for a list of ids) | The only way to obtain a verified document set; foreign ids are 404. |
| Retrieval | `Searcher` (hybrid, falls back to keyword) | Used by the `retrieved` read mode. |
| Citations | `escape_markup` and the strip-invalid-reference rule (`app/ai/rag.py`) | Same marker escaping; model `source_refs` are mapped to the units we sent, invalid ones stripped. |
| Provider layer | `LLMProvider`, `ModelRegistry`, `AiRuntime`, errors | Unchanged. `generate_structured` is used when the model supports it. |
| Prompts | Prompt registry and startup sync | New `study_*` entries (`app/ai/prompts/study.py`). |
| Usage and quotas | `AiUsageRecord`, `AiUsageRepository`, pricing, `RateLimiter` | New rows with `request_kind='generation'`; the daily token quota is shared with chat. |
| Background work | Celery app, `task_session_factory`, beat schedule, dispatcher pattern | New tasks `study.run_generation`, `study.dispatch_pending`, `study.sweep_stale_jobs`. |
| Ownership pattern | Composite FKs, `SetNullColumnsFK`, 404 for non-owned | Same on the new tables. |

Gaps found and filled (all small): `ScopeResolver.resolve_documents`; `FakeProvider.replies` (scripted replies for the invalid-then-corrected test); the worker had no LLM environment (compose `x-llm-env`); prompt registry gained entries.
Not rebuilt: extraction, OCR, chunking, embeddings, retrieval ranking, the citations UI, the chat orchestrator.

## 2. Module layout

```
backend/app/study/
  schemas.py          SourceSpec, GenerationRequest, fingerprint
  source_reader.py    SourceReader (ordered / sampled / retrieved / batches), SourceUnit, SourceBundle
  prompting.py        user turn (SOURCE blocks + TASK), correction turn, stored provenance
  validation.py       parse JSON, Pydantic validate, strip refs, duplicates, safe error text
  generators/         base.py (contract), registry.py, echo.py (M0 proof)
  engine.py           run_generation(): the pipeline for one job
  tasks.py, dispatch.py   Celery tasks, best-effort dispatch
  errors.py           safe codes and messages
backend/app/modules/study/   routes, service (limits, duplicates, ownership), schemas
backend/app/repositories/    generation_job_repository, study_material_repository, study_source_repository
backend/app/models/          study_material (+version), generation_job, study_preferences
```

## 3. Request flow

1. `POST /study/generations` (authenticated, CSRF, active account). The service checks: provider configured (503) and broker available (503), generator exists (422), settings valid (422, unknown fields rejected), every source id is the user's (404), something is ready to read (422), an identical active job (return it), then per-minute limit, daily quota, token quota and active-job cap (429). It inserts the job as `pending` and dispatches it (best effort). Response 202.
2. Worker `run_generation(job_id)`: **claim** (atomic `pending -> retrieving_sources`), **select model**, **read sources** (re-verified with `ScopeResolver`, because sources may have changed), context estimate and mode choice, **prompt**, **provider call** (`generating`), **validate** (`validating`, at most one correction call), **save** (`saving`: material, version 1 and the job's completion in one transaction).
3. The client polls `GET /study/generations/{id}`; on `completed` it reads `study_material_id` via `GET /study/materials/{id}`. `POST /study/generations/{id}/cancel` cancels.

Each stage commits in its own short transaction; no transaction is open while the provider works.

## 4. SourceReader

| Mode | Behaviour | Typical user |
|---|---|---|
| ordered | All chunks by document name, id, chunk index. Refuses (`GENERATION_SOURCE_TOO_LARGE`) if over budget. | summary, study guide |
| sampled | Evenly spaced chunks over the whole scope within the budget; `truncated` is reported. | flashcards, quiz, large scopes |
| retrieved | Hybrid search for a generator query; returned in reading order. | focused sets |
| batches | `ordered_batches(batch_tokens)`: consecutive batches covering every chunk exactly once. | map-reduce summaries (M1) |

Context estimate: stored `token_count` (else 1 token per 3 characters). Budget = min(`STUDY_MAX_INPUT_TOKENS`, 80 percent of the model's verified input limit) minus prompt overhead. The engine chooses ordered, sampled or refuse from what the generator declares.

## 5. Structured output

One Pydantic output model per generator. `validate_output` parses JSON (a Markdown fence is tolerated), validates the model, then runs the generator's `finalize` (duplicate detection, counts, source reference clean-up). Failures raise `OutputInvalid` with field paths and rule names only. The engine sends **one** correction request containing that text; a second failure ends the job (`GENERATION_INVALID_OUTPUT`). Maximum provider calls per job: 1, plus `STUDY_PROVIDER_MAX_RETRIES` transient retries, plus 1 correction.

## 6. Data model (migration 0004)

- `study_materials`: owner, workspace (composite FK to `workspaces(id, user_id)`), optional subject and chapter (cleared on delete), title, `resource_type`, `status`, `content` (structured result and source references), `generation_settings`, `source_metadata` (ids and counts), `current_version`, `archived_at`.
- `study_material_versions`: immutable snapshots, unique `(material, version_number)`, `origin`, `created_by`.
- `generation_jobs`: status, progress, model, prompt version, safe error code, request fingerprint (partial unique index on active statuses), `request` (ids and options), `source_stats` (counts), `provider_calls`, `cancel_requested`, heartbeat and timestamps.
- `study_generation_preferences`: user-set defaults (spec 16), one row per user.

## 7. Reliability and limits

See D-84 to D-88. Summary: atomic claim, no Celery auto-retry, no retry after a timeout, stale jobs failed and not restarted, cancel honoured mid-call, duplicate requests collapse to the active job, quotas per minute, per day, per active job count and tokens, size and time limits at every step, one usage row per provider attempt.

## 8. Security

Ownership at every step (404, never 403); source text and model output are never logged; model references and ids are never trusted; source text is data, not instructions (escaped markers, a rule in the system prompt); responses carry no source text, prompts or provider errors; the echo generator is refused in production.

## 9. What M1 to M8 add
The summary generator (map-reduce over `ordered_batches`), flashcards, quizzes (answer keys stored once, never returned before submission), guides, glossaries, formula sheets and question banks, the library API with versioning, editing, regeneration preview and export, the frontend, and the security review and acceptance.
