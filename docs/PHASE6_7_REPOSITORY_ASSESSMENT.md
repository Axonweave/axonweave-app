# Phase 6 / 7 Repository Assessment (Stage A)

Status: **Stage A only. No code, schema or feature changes were made.** Written 2026-11-13 on branch `docs/phase6-7-repo-assessment` from `main` at `454033c` (Phase 5 merged, PR #42).
Inputs read: `CLAUDE.md`, `docs/DECISIONS.md` (D-01 to D-121), the four Phase 6/7 spec documents named in the task (`PHASE6_7_MASTER_INSTRUCTIONS.md`, `PHASE6_SPEC.md`, `PHASE6_7_EXECUTION_AND_QUALITY.md`; `PHASE7_SPEC.md` was **not** read, as instructed), `docs/PHASE5_ACCEPTANCE.md`, and the real code (models, migrations, routes, repositories, services, Celery config, prompt registry, study engine, frontend routes, deps, CI).

**What was and was not verified.** Everything below comes from reading code. I did **not** run the backend, frontend or e2e test suites for this assessment, so "Phase 1-5 verified" means *implementation located and read*, not *tests re-run*. The Alembic head was checked earlier in the session: a single head, `0010`. The existing Phase 5 acceptance document is the only evidence of test results (not re-confirmed). A full regression run is a prerequisite for Stage C and should also be a baseline before Milestone 6.1.

**Phase 7 scope.** Because `PHASE7_SPEC.md` was not read, the Phase 7 sections here are limited to what the master and execution documents say (entity names, task names, routes). They need a second pass once the Phase 6 gate is passed.

---

## 1. Discrepancies between the spec documents and the repository (act on the code)

| # | Spec says | Repository reality | Proposed handling |
|---|---|---|---|
| 1 | Product is "ResearchMind AI" | Product is **Axonweave** everywhere (CLAUDE.md, UI, docs) | Keep Axonweave. Do not rename anything. Confirm with the owners. |
| 2 | Spec files at `docs/PHASE6_SPEC.md` etc. | They are in `docs/axonweave-phase6-7-specs/` (untracked) | Leave in place for now; decide whether to move them to `docs/` to match the convention of the earlier `PHASEn_SPEC.md` files. |
| 3 | "Enforce workspace ownership **and membership**" | There is no membership model: a workspace has one owner (`workspaces.user_id`). Rule 3 of CLAUDE.md scopes by owner. | Single-owner scoping only. No sharing/membership work. |
| 4 | Evidence rows store `supporting_text` (9.4, 10.3) | **D-82**: study materials store source *references*, never source text; CLAUDE.md rule 13: never log chunk text. Chunks are **deleted and recreated** on reprocess (see item 6). | Needs a decision (Q1). Recommendation: store a short, length-capped quote plus a hash, and never log it. |
| 5 | `knowledge_nodes.metadata` column | `metadata` is reserved on SQLAlchemy declarative models | Name the column `attributes` (or `extra`). |
| 6 | Evidence points at `chunk_id` | `DocumentChunkRepository.replace_for_version` **deletes and re-inserts chunks** for a version on reprocess, so chunk UUIDs are not stable | Evidence must not rely on a hard FK to `document_chunks.id`. Store `document_id`, `document_version_id`, `chunk_index`, page/slide, plus a nullable `chunk_id` for fast lookup, and mark evidence `stale` when its version is no longer active or the chunk disappears. |
| 7 | "Map questions by question tags" | **No question tags exist.** The only concept-like field is free-text `topic` (varchar 120) on `quiz_questions` and `flashcards` (D-102). Analytics group on that string. | Mapping must use `source_references` (document/chunk refs already stored on questions and cards) plus exact normalised-name/alias matching on `topic`. Ambiguous cases stay unresolved (spec 13.2). |
| 8 | "Extend Phase 5 recommendations" | `revision_recommendations.recommendation_type` has a CHECK of `quiz, flashcard, topic, chapter`; `target_id` has no FK; reasons are fixed-template text; D-119 forbids LLM-written text | Extend with a migration (new types, `knowledge_node_id`, structured explanation). Keep the rule engine deterministic. |
| 9 | Prompts/versions tracked | Prompts are an **in-code registry** (`app/ai/prompts/*.py`, highest version active, immutable once released); a `prompt_templates` table also exists | Add `knowledge_*` prompts to the in-code registry. Follow D-41/D-80. |
| 10 | CLAUDE.md rules 12 and 13 say "Do not implement … knowledge graph …" | Those prohibitions were scoped to Phases 2 and 3 | CLAUDE.md "What we are building" and rules 12/13/14 need a Phase 6 (and later 7) update; add decisions D-122+ (next free id). Not edited in Stage A. |
| 11 | Spec suggests `/knowledge`, `/learner` routes | Sidebar has a disabled "Research Studio (soon)" placeholder and no Knowledge/Learner entries; Progress is `/progress` | Extend `app-sidebar.tsx`; enable the Research placeholder only in Phase 7. |
| 12 | Task docs `PHASE6_IMPLEMENTATION_PLAN.md` etc. | Repo convention is `TASKS_PhaseN.md`, `PHASEn_ACCEPTANCE.md`, `*_ARCHITECTURE.md`, `DECISIONS.md` | Create the named docs but also add `TASKS_Phase6.md` and a `KNOWLEDGE_ARCHITECTURE.md` only if the owners want them (avoid competing documents, per spec 49). |

---

## 2. Existing architecture (what Phases 1-5 built)

**Stack as specified:** Next.js 16 (Turbopack, Cache Components) + React + TS + Tailwind + shadcn; FastAPI + SQLAlchemy 2 (async) + Alembic + Pydantic; PostgreSQL with pgvector; Redis; Celery worker and beat; S3-compatible object store (SeaweedFS); ClamAV; Squid egress proxy for the worker; Mailpit. Compose services: postgres, redis, objectstore, storage-init, worker, beat, egress-proxy, clamav, mailpit, backend, frontend.

**Layering** is as documented: `app/modules/<area>/{routes,schemas,service}.py` -> `app/repositories/*` -> `app/models/*`. Routers are registered in `app/api/v1/router.py` under `/api/v1`. Response envelope `{success,data}` / `{success:false,error:{code,message}}`.

**Ownership pattern (important for new tables).** Every row carries `user_id`; parent/child integrity is enforced in the database with composite FKs on `(id, user_id)`, e.g. `workspaces UNIQUE(id,user_id)`, `documents UNIQUE(id,user_id)`, `study_materials UNIQUE(id,user_id)`, FK `(workspace_id,user_id) -> workspaces(id,user_id)`. `subjects` have `UNIQUE(id, workspace_id)`; `chapters` have `UNIQUE(id, subject_id)`. New tables should reuse this pattern so cross-user references are impossible at the DB level.

**AI layer.** Provider-independent `app/ai/providers/` (base, Gemini, Fake), model registry (`model_registry.py`, `llm_models`, `llm_model_prices`), capabilities include `structured_output`, `generate_structured(request, schema)`, prompt registry in code, usage tracking (`ai_usage_records`, CHECK on `request_kind IN chat, embedding, generation, evaluation`), quotas, orchestration (`app/ai/orchestration`), RAG helper (`app/ai/rag.py`). Fake provider refuses `APP_ENV=production`.

**Document pipeline (Phase 3).** `app/ingestion` (extractors, normalise, chunker, pipeline, tasks, worker), `app/embeddings`, `app/retrieval` (`ScopeResolver`, searcher, embedder), `app/storage`. Chunks hold content, `page_number`/`slide_number`, `section_heading`, `bboxes`, `embedding`, `index_version`; document versions hold extraction metadata. Reads for generation are filtered to **active version + current index version** (`StudySourceRepository._active`).

**Study generation (Phase 4).** `app/study`: one engine (`engine.py`, 765 lines) with generator registry (summary, flashcards, quiz, study_guide, glossary, formula_sheet, question_bank, echo), `SourceReader` (ordered/sampled/retrieved read modes with token budgets), prompting with escaped untrusted SOURCE markers, Pydantic output validation, jobs with fingerprint de-duplication (partial unique index for one active job), cancel, heartbeat, stale sweeper, usage rows per provider attempt. The engine is **coupled to `study_materials`** (its save/preview steps write materials), so it is not directly reusable for graph extraction (see section 9).

**Assessment and revision (Phase 5).** Quizzes/attempts/answers with `grading_method`, `evaluation_status`, `evaluation_detail`; FSRS via py-fsrs 6.3.2 (`flashcard_scheduling` current state; `flashcard_reviews` append-only events with `previous_state`/`resulting_state`, idempotency key); `revision_sessions`; analytics derived by SQL (D-108, no stored aggregates); a rule-based recommendation engine with complete/dismiss endpoints.

**Celery.** Single default queue; `task_acks_late`, soft/hard limits from settings; beat schedule: storage cleanup (60 s), `ingestion.dispatch_queued` (60 s), `ingestion.sweep_stale_jobs` (120 s), `study.dispatch_pending` (60 s), `study.sweep_exports` (120 s), `study.sweep_stale_jobs` (120 s). Tasks: `ingestion.process_document`, `study.run_generation`, export task. Pattern: API enqueues; DB row is the source of truth; a beat dispatcher re-enqueues pending rows (so Redis loss is survivable); workers claim jobs with an atomic status update (D-85).

**Tests/CI.** `backend/tests/` (ai, documents, ingestion, retrieval, revision, storage, study plus root security/auth tests). CI (`.github/workflows/ci.yml`): ruff, mypy, alembic upgrade, single-head check, pytest with **coverage >= 85%**; frontend lint, `tsc`, Vitest, build; Playwright e2e against the full stack (fake LLM provider). Browser specs: academic, ai-tutor, auth, dashboard-pages, journey, library, revision, settings, study.

---

## 3. Existing tables and relationships (migrations 0001 to 0010, single head)

Core: `users`, `sessions`, `user_profiles`, `user_preferences`, `email_verification_tokens`, `password_reset_tokens`, `activity_logs`, `workspaces`, `subjects`, `folders`, `chapters`.
AI: `llm_providers`, `llm_models`, `llm_model_prices`, `prompt_templates`, `conversations`, `messages`, `message_feedback`, `message_citations`, `ai_usage_records`.
Documents: `documents`, `document_versions`, `document_chunks`, `document_processing_jobs`, `storage_cleanup`.
Study: `generation_jobs`, `study_materials`, `study_material_versions`, `study_generation_preferences`, `study_exports`, `flashcard_sets`, `flashcards`, `quizzes`, `quiz_questions`, `quiz_attempts`, `quiz_attempt_answers`.
Revision: `flashcard_scheduling`, `flashcard_reviews`, `revision_sessions`, `revision_recommendations`.

Hierarchy: `users -> workspaces -> subjects -> {folders (self-nesting), chapters}`; `documents` carry denormalised `workspace_id`, `subject_id`, `folder_id`, `chapter_id` (plus versions and chunks that repeat these ids for scoped queries); `study_materials -> {flashcard_sets -> flashcards, quizzes -> quiz_questions}`; `quiz_attempts -> quiz_attempt_answers`; `flashcards -> flashcard_scheduling` and `flashcard_reviews`.

**Facts that matter for Phase 6:**
- `quiz_questions` and `flashcards` have **no workspace/subject columns**; they reach the workspace through `quizzes/flashcard_sets -> study_materials`.
- Both have `source_references` JSONB (document/chunk refs, page/slide) and a free-text `topic`.
- `quiz_attempt_answers` is the per-question event (correctness, score, `grading_method`, `ai_assisted`, `evaluation_detail`); `flashcard_reviews` is the per-review event. These are the two canonical learner event sources (matches spec 13.1).
- `generation_jobs.generation_type` has **no CHECK constraint** (only `study_materials.resource_type` does).
- Deleting a user cascades through everything (D-110); account export (D-24) lists data classes and must be extended.

---

## 4. Existing API endpoints (159 route handlers under `/api/v1`)

`/auth` (register, login, logout, me, forgot/reset password, verify/resend email) | `/users/me/*` (profile, preferences, sessions, password, email, export, delete) | `/workspaces`, `/workspaces/{id}/subjects`, `.../folders`, `.../chapters` (CRUD, archive/restore, reorder) | `/dashboard/*` | `/documents/*` (upload, replace, list, detail, status, retry, reprocess, cancel, download, inline, pages, content, archive/restore/delete) | `/search` | `/citations/{id}`, `/documents/{id}/sources/{chunk_id}` | `/ai/*` (conversations, messages, regenerate, cancel, feedback, usage, models, status, capabilities) | `/study/generators`, `/study/generations*`, `/study/materials*` (get, patch, versions, restore, regenerate, library, duplicate, archive, export, glossary, questions) | `/study/flashcards*` | `/study/quizzes/{id}/attempts*`, `/study/quiz-attempts` | `/revision/*` (due, overdue, new, cards, summary, sessions) and `/study/flashcards/cards/{id}/*` (schedule, review, suspend, review-history) | `/analytics/*` (overview, quiz-performance, subject-performance, topic-performance, revision-activity, study-calendar, streaks) | `/recommendations/*` (revision, weak-topics, complete, dismiss).

**No existing route collides with `/knowledge/*` or `/learner/*`.** The suggested `/recommendations/{id}/complete|dismiss` already exists and must stay backward compatible.

---

## 5. Reusable backend infrastructure (extend, do not rebuild)

| Need in Phase 6 | Reuse | Notes |
|---|---|---|
| Owner scoping of documents/chunks | `ScopeResolver`, `StudySourceRepository._active` | Foreign ids return 404. Active version and index version already filtered. |
| Reading chunks within a token budget | `SourceReader` (ordered / sampled / retrieved) | Ordered batching exists for long documents; extraction can use ordered batches per chapter/document. |
| Prompt injection protection | `study/prompting.py` escaped SOURCE markers (D-80) | Use the same marker and escaping for extraction prompts. |
| LLM call, structured output, validation, one correction retry | `engine._validated_call`, `_call`, `_await_provider`, `_select_model`, `_input_budget`, `_output_cap` | Private to the engine today (see section 9). |
| Provider/model selection, no hardcoded ids | model registry (`STUDY_GENERATION_MODEL` pattern) | Add `KNOWLEDGE_EXTRACTION_MODEL` style setting. |
| Usage and quotas | `ai_usage_records`, per-user token quota, usage service | Needs new `request_kind` values (CHECK migration). |
| Background job pattern | `GenerationJob` model + `study/tasks.py` + `dispatch.py` + sweeper + fingerprint partial unique index | Copy the pattern for extraction jobs. |
| Evidence deep links | `/documents/{id}/sources/{chunk_id}`, viewer `?page=&chunk=` query params | Already supported by `documents/[documentId]/page.tsx`. |
| Idempotent events | unique `(user_id, idempotency_key)` on `flashcard_reviews`; `submit_idempotency_key` on attempts | Learner evidence uses `(user_id, source_type, source_event_id)` unique. |
| Time zones, day windows | D-111 helpers in `analytics/logic.py` | Reuse for "due", "recent". |
| Topic statistics | `AnalyticsRepository.topic_attempt_rows`, `struggle_by_topic`, `overdue_by_topic` | Group by `topic` text. Phase 6 must reconcile text topics with nodes, not replace these. |
| Recommendation lifecycle | `RecommendationService` (rules, `sync`, `resolve`), `RecommendationRepository` | Extend rules; keep existing routes. |
| Ownership / rate limits / CSRF | `core` security dependencies, per-route rate limits | Apply to all new routers. |

## 6. Reusable frontend infrastructure

Pages and layout: `(app)` route group with `app-sidebar.tsx` (config array with `disabled` flag), shared `components/ui` (button, dialog, alert-dialog, confirm-dialog, dropdown-menu, input, label, toast/toaster, pager, `async-section` with `loading.tsx`, `empty-state`, `error-display`), `components/forms`, hooks `use-async`, `use-auth`, `use-toast`, generated API types in `src/types/api.generated.ts` (`npm run generate-types`).
Feature folders: `academic`, `activity`, `ai-tutor`, `archived`, `auth`, `dashboard`, `documents` (library, detail, `pdf-viewer` with highlight support), `revision`, `study`, `workspaces`.
Charts: **no chart library**; Phase 5 uses small hand-written SVGs with theme `--chart-*` tokens and adjacent tables (D-121). Markdown rendering via `react-markdown` + `rehype-sanitize`; maths via `katex`.
**Missing:** any graph-visualisation library (`package.json` has none). Introducing one needs the bundle-size, maintenance, accessibility and compatibility assessment required by spec 12.2 (open question Q3). CI e2e specs run against a Compose build; new pages require rebuilding the `frontend` image.

---

## 7. Existing AI, task and worker infrastructure (summary of constraints)

- Worker can reach the LLM only through the Squid allow-list (D-77); `GEMINI_API_KEY` is passed to the worker. Knowledge extraction in the worker needs no new egress.
- The API process never calls a provider for generation (D-84). Extraction must run in Celery.
- No automatic Celery retry for LLM work (D-85): duplicates are prevented by atomic claim; provider "busy/unavailable" retried a bounded number of times; timeouts are never retried. Phase 6 tasks should inherit these rules.
- Single queue and shared time limits; long extraction/recalculation may need its own soft/hard limits (as `study.run_generation` has).
- App must work with no provider (503 `LLM_NOT_CONFIGURED`), and without Redis/worker: Phase 6 endpoints that need the worker must degrade the same way (only the extraction endpoints answer 503); learner mastery over existing evidence should not need an LLM at all (rule-based, spec 14).

---

## 8. Missing functionality (Phase 6)

Everything in Phase 6 is absent: no knowledge tables, no extraction, no concept mapping, no learner evidence store, no mastery engine, no misconception detection, no graph UI, no learner-intelligence UI. Recommendations exist but are topic-text rules only. Concretely missing building blocks: a concept identity that spans documents; a link between quiz questions/flashcards and concepts; a per-concept learner state; a place to store model/prompt versions for extraction; graph traversal queries; a graph rendering component.

## 9. Potential conflicts and risks

1. **Chunk instability (high).** Reprocess/replace recreates chunks (item 6). Evidence tied to chunk ids would break or silently dangle. Need version-aware evidence and a staleness/re-link strategy, and a hook (or a periodic check) when a document version is replaced or deleted. Deleting a document must delete or mark derived concepts per the retention policy (spec 6 "derived records").
2. **Engine coupling (high).** `StudyEngine` writes study materials. Generalising it risks regressions across seven generators and the 285 test functions under `backend/tests/study` (counted by `def test_`, not executed). Recommendation: build a sibling package `app/knowledge/` that **reuses** `SourceReader`, prompting helpers, provider/registry, usage tracking and the job pattern, and extract only the small shared LLM-call helper if needed, in its own reviewed change, not inside 6.1.
3. **Source text vs D-82 / rule 13 (medium).** Evidence `supporting_text`. Decision required (Q1).
4. **Topic strings vs nodes (medium).** Phase 5 analytics, recommendations and `revision_recommendations.topic_name` are keyed by topic text. Introducing nodes must not change existing Phase 5 outputs; mapping is additive.
5. **`ai_usage_records` CHECK (low, certain).** New `request_kind` values require a migration like 0010.
6. **Recommendation table constraints (low, certain).** CHECK on type and no FK on `target_id`; widening is a migration and changes the meaning of `target_id` (polymorphic) - add a typed `knowledge_node_id` instead.
7. **Mastery and misconception privacy (medium).** Misconception detection reads the learner's answer text. It must be passed as untrusted data, never logged (rules 12/13), and the stored explanation must not copy the answer wholesale. Needs a retention rule (D-110 style: cascade on question/attempt/account deletion).
8. **Graph size and N+1 (medium).** Spec forbids unbounded traversal. Postgres recursive CTEs with depth and node limits; indexes on `(user_id, source_node_id)`, `(user_id, target_node_id)`, and scoped node search (trigram/GIN) - no migration or code references `pg_trgm` today (check availability in the Postgres image before relying on it; the existing text search is `tsvector`).
9. **Merge semantics (medium).** Merging nodes must re-point edges, evidence, aliases, learner evidence, states and recommendations atomically and keep an audit trail (`knowledge_merge_history`, which the spec lists as optional; I consider it required for undo and for deduplicating learner evidence after a merge).
10. **User edits vs reprocess (medium).** "Do not silently overwrite user-edited concepts": nodes need an `edited_by_user` / `origin` marker and extraction must create proposals or skip edited nodes.
11. **Coverage gate (low).** CI requires >= 85% coverage over `app`; new modules need tests from the start.
12. **Frontend graph library (medium).** No library present; accessibility of canvas-based graphs is poor; a list/table alternative view for keyboard and screen-reader users should be part of 6.4.
13. **Environment fragility seen this session.** The local database started un-migrated and the frontend `node_modules` was out of date; neither is a repo defect but the setup docs should say "run `alembic upgrade head` and `npm install` after pulling".
14. **Phase 4/5 live-provider behaviour is unverified** (Phase 5 acceptance: live-provider grading not verified), so extraction quality against a real model is an unknown until measured; fixtures use the fake provider.

---

## 10. Required schema changes (Phase 6)

Reviewed against the existing schema; none of the proposed entities already exist. All follow the `(id, user_id)` composite-FK ownership pattern, UTC timestamps, UUID keys, explicit delete behaviour (`ON DELETE CASCADE` from `users`/`workspaces`; derived rows removed or marked stale when a source goes).

| Table | Purpose / notes | Differences from the spec's suggestion |
|---|---|---|
| `knowledge_nodes` | Concepts. `user_id`, `workspace_id` (composite FK), nullable `subject_id`, nullable `chapter_id`, `name`, `normalised_name`, `description`, `definition`, `node_type` (CHECK list), `difficulty` (nullable), `attributes` JSONB, `origin` (`extracted`/`user`), `edited_by_user`, `archived_at`, timestamps. Unique `(user_id, workspace_id, normalised_name, node_type)` among non-archived nodes; `UNIQUE(id,user_id)` and `UNIQUE(id,workspace_id)`. | `metadata` renamed `attributes`; adds origin/edit flags and `chapter_id`. |
| `knowledge_node_aliases` | Aliases used for matching (spec lists as optional; matching rules in 9.6 make it required). Unique `(user_id, workspace_id, normalised_alias)` -> node. | Promoted from optional to required. |
| `knowledge_edges` | `source_node_id`, `target_node_id` (composite FKs, same workspace), `relationship_type` (CHECK: IS_A, PART_OF, PREREQUISITE_OF, DEPENDS_ON, RELATED_TO, CONTRASTS_WITH, USES, APPLIED_IN, EXAMPLE_OF), `description`, `confidence`, `statement_kind` (`stated`/`inferred`), `origin`. CHECK `source <> target`; unique `(user_id, source, target, type)`; indexes for both traversal directions. Symmetric types (RELATED_TO, CONTRASTS_WITH) stored once with canonical ordering. | Adds stated/inferred (spec 9.5) and symmetric canonicalisation. |
| `knowledge_evidence` | `knowledge_node_id` and/or `knowledge_edge_id` (CHECK at least one), `document_id`, `document_version_id`, `chunk_index`, nullable `chunk_id` (no hard FK), `page_number`, `slide_number`, `quote` (length-capped, see Q1) + `quote_hash`, `evidence_type`, `extraction_method`, `extraction_job_id`, `confidence`, `stale` boolean. | `source_type/source_id` replaced by explicit document columns (documents are the only source in 6.1). |
| `knowledge_extraction_jobs` | Mirrors `generation_jobs`: status, progress, heartbeat, cancel flag, celery id, fingerprint with partial unique index (one active job per fingerprint), `extraction_version`, `prompt_version`, `model_id`, safe `error_code` (not free-text `error_message`), counts, timestamps. Source: document and optional chapter. | `error_message` replaced by safe code (rule 6); fingerprint added (D-87). |
| `knowledge_duplicate_candidates` | Reviewable merge suggestions (spec 9.6; listed there as "knowledge_extraction_candidates"). Pair of nodes, signals used, status (`open`/`merged`/`kept_separate`/`related`/`ignored`). | Required by 9.6. |
| `knowledge_merge_history` | Audit of merges (needed for undo/dedup after merge). | Promoted from optional. |
| `knowledge_concept_links` | Maps a quiz question or flashcard to a node: `source_type` (`quiz_question`/`flashcard`), `source_id`, `knowledge_node_id`, `method` (`source_reference`/`exact_name`/`alias`/`user`), `status` (`confirmed`/`proposed`/`rejected`). | **Not in the spec**; needed for 13.2 ("reviewed mappings", unresolved state). |
| `learner_evidence` | Canonical events. `knowledge_node_id` **nullable** (unmapped evidence stays, 13.7), `source_type` (`quiz_answer`/`flashcard_review`), `source_event_id`, `evidence_value` numeric, `evidence_metadata` JSONB (difficulty, question type, rating, interval, lapses), `occurred_at`. **UNIQUE `(user_id, source_type, source_event_id, knowledge_node_id)`** for idempotent ingestion. | Dedup key defined; aggregates (attempt summaries) are *never* ingested, only per-answer and per-review events (13.5). |
| `learner_concept_states` | Unique `(user_id, knowledge_node_id)`: mastery, confidence, evidence_count, `state` (CHECK: NOT_ASSESSED, INSUFFICIENT_EVIDENCE, LEARNING, DEVELOPING, PROFICIENT, STRONG), `calculation_version`, structured `explanation` (JSONB of evidence ids used, plus rendered text). Derivable and rebuildable from `learner_evidence`. | Explanation stored as structured data so it is reproducible and testable. |
| `learner_misconceptions` + `learner_misconception_evidence` | As spec; status (`suggested`/`confirmed`/`dismissed`/`corrected`), confidence, `detection_version`, `prompt_version`, `model_id`; evidence rows reference `quiz_attempt_answers`/`flashcard_reviews` ids. | |
| `revision_recommendations` (**extend**) | Widen type CHECK; add `knowledge_node_id` (FK, nullable), `source` (`phase5_rule`/`learner_rule`), structured `evidence` JSONB, `rank_score` components. Keep `dedupe_key`, status, complete/dismiss. | Spec's optional `learner_recommendations` table is **not** created. |
| `ai_usage_records` (**alter CHECK**) | Add request kinds such as `extraction`, `misconception`. | |
| `generation_jobs` | No change expected. | |

**Proposed migrations (each small, reversible, one head):**

| Id | Content | Milestone |
|---|---|---|
| 0011 | `knowledge_nodes`, `knowledge_node_aliases`, `knowledge_edges`, `knowledge_evidence` (+ indexes, constraints) | 6.2 |
| 0012 | `knowledge_extraction_jobs`, `knowledge_duplicate_candidates`, `knowledge_merge_history`, `ai_usage_records` kind CHECK | 6.1/6.2 (jobs table is needed first by 6.1; order to be fixed in the implementation plan) |
| 0013 | `knowledge_concept_links`, `learner_evidence` | 6.5 |
| 0014 | `learner_concept_states` | 6.6 |
| 0015 | `learner_misconceptions`, `learner_misconception_evidence` | 6.7 |
| 0016 | `revision_recommendations` extension | 6.8 |

Also: a `pg_trgm` extension migration only if justified by search measurements (see risk 8). Tests required per the execution document: upgrade on a clean database, upgrade on a database already holding Phase 1-5 data, and downgrade for each migration.

**Other required non-schema changes:** new settings/env placeholders in `.env.example` (extraction model, limits, quotas, concept caps per job), prompts `knowledge_extract_concepts`, `knowledge_extract_relations`, `knowledge_misconception` (versioned), Celery tasks and beat entries (dispatcher, stale sweeper, recalculation), account-export and deletion coverage (D-24, D-110), CLAUDE.md and DECISIONS updates, OpenAPI type regeneration, sidebar and routes.

---

## 11. Dependency relationships

```
Phase 3 documents/chunks (active version, index_version)
  -> 6.1 extraction (SourceReader, prompts, provider, usage)  -> 6.2 knowledge tables
  -> 6.3 services/APIs  -> 6.4 graph UI
Phase 4 quiz/flashcard source_references + topic  --\
Phase 5 quiz_attempt_answers + flashcard_reviews   ---> 6.5 concept links + learner_evidence
                                                    -> 6.6 mastery -> 6.7 misconceptions (needs 6.3 graph + 6.5 evidence)
                                                    -> 6.8 recommendations (needs 6.3 graph + 6.6 + 6.7 + Phase 5 rules)
                                                    -> 6.9 dashboard (needs 6.3 APIs + 6.6/6.7/6.8) -> 6.10 acceptance
```
Hard dependencies: 6.5 needs concepts to exist (6.2); 6.7 and 6.8 need 6.6; 6.9 needs everything before it. 6.1 can be built and tested against the fake provider before 6.2's migration only if the persistence step is behind a repository interface; otherwise do 6.2's migration first. (The spec orders 6.1 before 6.2; I recommend keeping the spec order but landing migration 0011 at the start of 6.1.)

## 12. Recommended implementation sequence

Follow the spec's stage order; adjustments are within milestones, not reorderings.

0. **Baseline (before 6.1):** run the full backend, frontend, e2e suites on `main` and record the numbers; record the tests-green baseline in the plan. Decide Q1 to Q5. Update `CLAUDE.md` and add decisions D-122+ for each answer.
1. **6.1 + 6.2:** `app/knowledge/` package (extraction pipeline, schemas, validators: every concept/edge needs resolvable evidence verified against actual chunk text, hallucinated references dropped), migrations 0011-0012, jobs, tasks, duplicate candidates. Evaluation fixtures generated in code (D-76). Prompt-injection and malformed-output tests.
2. **6.3:** services, repositories, routes (`/api/v1/knowledge/*` as in the spec), bounded traversal (depth <= 3, node cap, pagination), merge with history, cross-user tests.
3. **6.4:** graph UI. Decision on library (Q3); evidence navigation via the existing viewer links; list alternative view; mobile.
4. **6.5:** `knowledge_concept_links`, `learner_evidence`, ingestion from per-answer and per-review events (hooks plus a backfill/rebuild job, idempotent).
5. **6.6:** deterministic versioned mastery calculator (pure function, documented weights and thresholds, golden tests); recalculation triggers; states never label unassessed as weak.
6. **6.7:** misconception detection (LLM on bounded evidence, threshold on repeated evidence count, structured output, dismiss/correct).
7. **6.8:** extend recommendations (additive rules with explanation structure); keep Phase 5 rules and endpoints green.
8. **6.9:** Learner Intelligence pages; integrate with Progress by linking, not duplicating.
9. **6.10 / Stage C:** acceptance report, Phase 1-5 regression, security/ownership tests, migration checks on populated data.
**Phase 7 (Stage D)** is not planned here (spec not read); expected reuse points are `documents`/ingestion (papers), the graph (milestone 7.10), `ScopeResolver`, the study engine pattern and `generation_jobs`-style job tables; this must be re-assessed against `PHASE7_SPEC.md` at the Phase 6 gate.

---

## 13. Questions that need an owner decision before implementation

- **Q1 (evidence text):** may `knowledge_evidence` store a short capped quote of source text (contradicts the letter of D-82), or only references + hash and re-read the text from the active chunk at display time (safer, but breaks when a chunk changes)? *Recommendation:* store a short quote (<= ~300 chars), never log it, delete with the evidence; record as a new decision.
- **Q2 (extraction scope/cost):** default extraction unit (whole document vs chapter), per-job limits on concepts, per-user daily limits and whether extraction counts toward the existing daily token quota.
- **Q3 (graph library):** accept a new frontend dependency for graph rendering (candidates to be evaluated in 6.4: `react-flow`/`@xyflow/react`, `cytoscape`, or `d3-force` with a hand-written SVG layer in the style of D-121) or stay dependency-free with a layered/hierarchical SVG layout. Needs a bundle and accessibility assessment first.
- **Q4 (product name and doc locations):** confirm Axonweave naming and where the spec documents live.
- **Q5 (CLAUDE.md update):** confirm Phase 6 may now relax rules 12-14 that forbade the knowledge graph, and who edits `CLAUDE.md` (shared file; smallest possible change).

## 14. Stage A completion status

COMPLETE for Phase 6 planning. Phase 7 assessment is intentionally **deferred** (spec withheld by instruction). No schema, feature or test changes were made. Awaiting review before Stage B.
