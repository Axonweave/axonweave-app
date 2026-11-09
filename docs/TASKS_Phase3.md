# Task board and ownership (Phase 3: Document Intelligence and RAG)

Requirements: `PHASE3_SPEC.md`. Design: `DOCUMENT_ARCHITECTURE.md`. Review and conflicts: `DOCUMENT_INTELLIGENCE_PLAN.md`. Decisions: `DECISIONS.md` D-62 to D-76.
Tick a task only when its PR is merged to `main`. Ownership is filled in when work is assigned. One branch per task, Conventional Commits,
no push to `main`, one Alembic head. Every milestone ends with ruff, mypy, pytest, Vitest (and Playwright from M6) green.

## Shared files (change minimally, mention in the PR)
`backend/app/api/v1/router.py`, `backend/app/main.py`, `backend/app/models/__init__.py`, `backend/requirements.txt`, `backend/Dockerfile`,
`docker-compose.yml` (every new variable under `backend.environment` and the worker/beat services; there is no `env_file`), `.env.example`,
`.github/workflows/ci.yml`, `frontend/package.json`, `frontend/next.config.ts` (CSP), `backend/app/modules/users/service.py` (export, deletion),
`frontend/src/components/layout/app-sidebar.tsx`, `backend/app/core/rate_limit.py`, `backend/app/ai/orchestration/*` (RAG hook).

## Preconditions
- [ ] This planning PR (`docs/phase3-plan`) approved and merged; `main` green in CI.
- [ ] Gemini key available locally as `GEMINI_API_KEY` (never committed or pasted). Provider-side spending limit set; embedding calls cost money.
- [ ] Open item from Phase 2 not blocking, but recorded: key rotation confirmed; model price verified (D-39).
- [ ] `.env.example` placeholders from `docs/PHASE3_ENV_PLACEHOLDERS.md` pasted in (the planning session could not edit that file).

## M1: Infra, storage and schema  Owner: ________
- [ ] Verify and record (date, version): pgvector image tag and installed pgvector version; SeaweedFS image tag and S3 API behaviour needed (D-62, D-63). Re-check that MinIO CE status has not changed the choice.
- [ ] `docker-compose.yml`: pgvector Postgres (init scripts still work), `redis`, `worker`, `beat`, object store + bucket bootstrap; worker network restricted (D-70); healthchecks. Phase 1/2 stack still starts without the new services.
- [ ] `backend/Dockerfile`: separate `worker` target with Tesseract/OCR packages; API image unchanged and parser-free.
- [ ] CI: Postgres service with pgvector, Redis service; e2e stack includes worker and store. Fix the 29 pre-existing `format:check` warnings in a separate chore before adding that script to CI.
- [ ] Settings: storage, Redis, Celery, embedding, limits, retrieval; production guards (no fake embedder, no in-memory storage, no placeholder keys) (D-64, D-69).
- [ ] `storage/` (`StorageBackend`, S3, in-memory, key builder) with tests: key never contains user input, traversal names impossible, SDK import-boundary test.
- [ ] Models + migration(s): extension (owner), `documents`, `document_versions`, `document_processing_jobs`, `document_chunks` (composite FKs, generated tsvector + GIN, bboxes, index_version), `storage_cleanup`, `message_citations`, `conversations.scope_*`, `messages.scope_*`/`answer_mode`, `ai_usage_records.request_kind` (D-67). Constraints on models (D-61); migrated schema equals metadata; grants verified as `axonweave_app`; one head.
- [ ] Schema tests: cross-owner rows rejected by the database, one running job per version, unique chunk index, scope CHECK, composite chain (folder/chapter belong to subject).
- [ ] Measure and record pgvector filtered-search behaviour on synthetic data (exact vs HNSW with `hnsw.iterative_scan`) to prepare D-73.
- Done when: the stack runs with the new services, the schema is migrated and tested, storage round-trips on both backends, Phase 1/2 suites unchanged and green.
  - Status (branch `feat/docs-infra-schema`, not yet merged, so boxes stay unticked): built and verified locally; see the PR for the verified / not verified list.
  - Not part of this PR, still open for M1: the pgvector filtered-search measurement (needs real embeddings, moved to M4 with the evaluation set) and the pre-existing `format:check` chore.
  - Changed from the plan while building: messages also get `scope_type`/`scope_id`/`answer_mode` (D-67); the chunk scope columns have no FKs (informational, never used for authorisation); `.env.example` still needs the block from `docs/PHASE3_ENV_PLACEHOLDERS.md` pasted by a human.

## M2: Upload and document management API  Owner: ________
- [ ] Spike first: stream a large multipart upload through the real middleware stack (CSRF, security headers, correlation id) with the size cap enforced; convert to pure ASGI only if needed.
- [ ] `documents` module: upload (streamed, 413, magic bytes, sanitised names, zip/image bounds, quotas, optional `Scanner`), list (filters, pagination, allow-listed sorts), get, patch (rename, move with chunk scope update), archive, delete, status, download (attachment), inline endpoint (D-72).
- [ ] One delete service used by document, folder, chapter, subject, workspace and account deletion; writes `storage_cleanup` first; Celery cleanup task + reconciliation (D-66).
- [ ] `RedisRateLimiter` with in-process fallback and security event (D-65); upload and search limits; existing callers unchanged.
- [ ] Account deletion removes documents and objects; export adds document metadata only.
- [ ] Tests: cross-user 404 on every route, unauthenticated 401 sweep (OpenAPI walk), oversize/zip-bomb/image-bomb/spoofed-MIME/path-traversal-name/HTML upload rejected, quotas, rate limit with Redis down, delete leaves no object, cascade paths each enqueue cleanup, export has no content.
- Done when: documents can be uploaded (stored, row created, job queued, status `queued`), listed, renamed, moved, downloaded, deleted, with no processing yet.

## M3: Extraction, OCR, normalisation and chunking pipeline  Owner: ________
- [ ] Celery app, tasks, retry limits, timeouts, heartbeat, cancel flag, sweeper for stuck jobs and unsent `queued` jobs (D-68, D-74).
- [ ] Extractors: PDF (PyMuPDF; pages, blocks, bboxes), PPTX (slides, tables, notes), DOCX (headings, tables, lists), text/markdown, images; OCR only for pages without digital text; confidence; warnings.
- [ ] Normalisation and structure detection; structure-aware chunker with provenance; configurable size and overlap; token counting.
- [ ] Idempotent write stage (delete-and-rebuild in one transaction), status mirroring, safe error codes, retry/reprocess endpoints, pages/content endpoints.
- [ ] Generated fixtures (PDF, scanned-style PDF, PPTX, DOCX, hostile files); no copyrighted files in git (D-76).
- [ ] Tests: each format, empty/corrupt/password-protected, large document limits, page/slide provenance, no duplicate chunks on retry or redelivery, concurrent duplicate jobs, timeout and memory limit, no document text in logs.
- Done when: an uploaded fixture reaches `completed` with correct chunks (without embeddings yet, stage stubbed by the fake embedder in tests only).

## M4: Embeddings and retrieval  Owner: ________
- [ ] `EmbeddingProvider`, registry, `FakeEmbeddingProvider`, Gemini adapter; `scripts/list_embedding_models.py`; **verify and record the model id, dimension and date in D-69** (D-69, D-38 style).
- [ ] Embedding stage: batching, rate limits, retries in the orchestration layer, usage rows (`request_kind = embedding`), quota accounting, `index_version`; extend the privacy notice (D-54).
- [ ] `ScopeResolver` and `SourceReader` (types that cannot be built from raw ids); `Searcher` (exact filtered vector, full-text, RRF, threshold, budgeted selection); `POST /search`.
- [ ] Evaluation set and runner (Recall@K, Precision@K, MRR) on generated fixtures and `testdata-private/`; measure exact vs ANN with the real filters; add an index only if justified; record results (no document text).
- [ ] Version switch (one transaction); deleted documents and inactive versions never returned; reindex path for a new embedding model.
- [ ] Tests: keyword/semantic/hybrid, each scope type, user isolation (cross-user chunks never returned, foreign document id as scope = 404), deleted/inactive excluded, dimension/model mismatch rejected.
- Done when: a user can search their own documents with correct scoping and measured quality.

## M5: RAG and citations  Owner: ________
- [ ] `DocumentContextSource` plugged into `ContextManager`; `rag_*` prompts (versioned, D-41); delimiter escaping; answer modes; fixed insufficient-evidence reply without an LLM call; follow-up query building (D-75).
- [ ] Conversation scope (validated, stored); per-message scope/mode; SSE `message.citations` before the first delta; validated completion; `[n]` stripping; `message_citations` persisted; citation and source-passage endpoints with ownership checks.
- [ ] Deleted-document behaviour for citations (D-66).
- [ ] Tests on the fake provider: grounded answer, insufficient evidence, multiple sources, contradictory passages, follow-ups, forged/invalid citation stripped, prompt injection inside a document, other user's document as scope = 404, cancelled stream keeps citations consistent, usage correct, no content in logs.
- [ ] One real-provider run through the API recorded honestly (as in Phase 2).
- Done when: document-grounded streaming answers with verified citations work end to end on the fake provider and via the API on the real one.

## M6: Frontend  Owner: ________
- [ ] Enable Library in the sidebar (D-59 pattern: sidebar, Vitest assertion, Help text in the same PR); routes `(app)/library`, `(app)/documents/[documentId]`; extend the no-store rule and CSP `worker-src` (D-72).
- [ ] `features/documents`: upload zone (drag and drop, multiple, progress, cancel, validation messages), list with filters and real status polling, retry, delete with confirmation, upload from subject/folder/chapter pages.
- [ ] Document detail: metadata, processing info, extracted content by page/slide/section, pdf.js viewer (page, zoom, search, citation navigation, highlight where bboxes exist).
- [ ] AI Tutor: scope selector and breadcrumb, answer-mode selector with a clear indicator, citations UI, source panel, insufficient-evidence state, not-configured states (storage/Redis/embedder), accessible and responsive to 375 px.
- [ ] Vitest for components and the stream parser changes; Playwright flows: upload -> processing -> ask -> cite -> open source -> delete; second-user isolation; mobile.
- Done when: the whole spec section 1.3 flow works in the browser on the fake providers.

## M7: Security, evaluation, docs and acceptance  Owner: ________
> Status 2026-11-09: M1 to M6 are merged (PRs #23 to #26). Per-item boxes above M7 were not individually re-ticked; see `docs/PHASE3_ACCEPTANCE.md` for the evidence-based status. Open in M7: human faithfulness check, load tests, worker egress for embeddings.
- [x] Security review against spec 21 and 22.5 (all ten cases mapped to named tests); gitleaks, `pip-audit`, `npm audit`; bundle scan; worker isolation checked (no outbound network, limits enforced); written up in `docs/DOCUMENT_SECURITY.md`.
- [ ] RAG evaluation documented (`docs/RAG_EVALUATION.md`): retrieval metrics, citation correctness, faithfulness spot-check by a person (not scored by the model alone), limits and costs.
- [ ] Load/failure tests: worker crash mid-job, Redis down, storage down, embedder rate-limited, duplicate delivery, large upload, many small uploads.
- [ ] Docs: update `AI_ARCHITECTURE.md` (as-built), `SETUP.md`, `DEPLOYMENT.md` (Redis, worker, storage, backups of object store), `BACKUP_RESTORE.md`, `WORKFLOW.md`, `README.md`, API reference; privacy notice text.
- [x] `docs/PHASE3_ACCEPTANCE.md` written honestly against spec section 23 (Met / Partly / Not met with evidence).
- [ ] CI green on `main` for backend, frontend, e2e (with worker/store) and security jobs.
- Done when: every section 23 criterion is met or honestly listed as open.

## Out of scope (do not start)
Everything in Phase 3 spec section 24: automatic flashcards, quiz generation, full study-guide generation, spaced repetition, adaptive learning,
knowledge graph, research gap/contradiction analysis, audio summaries, podcast generation, video understanding. Also not in Phase 3: reranker
(until baseline is measured), LLM query rewrite (flag, later), rendered PPTX/DOCX previews, legacy `.doc`/`.ppt`.
