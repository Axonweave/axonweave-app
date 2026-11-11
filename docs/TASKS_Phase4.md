# Task board and ownership (Phase 4: AI-Powered Study Generation)

Requirements: `PHASE4_SPEC.md` (sections 1 to 27). Decisions: `DECISIONS.md` from D-78 onward (written by M0). Autopilot prompts: `docs/prompts/P4-*.md`.
Tick a task only when its PR is merged to `main`. One branch per task, Conventional Commits, no push to `main`, one Alembic head.
Every milestone ends with ruff, mypy, pytest, Vitest (and Playwright from M6) green. Phase 4 builds on Phase 3: do not rebuild ingestion, retrieval or citations (spec section 27).

## Shared files (change minimally, mention in the PR)
`backend/app/api/v1/router.py`, `backend/app/main.py`, `backend/app/models/__init__.py`, `backend/requirements.txt`, `docker-compose.yml`, `.env.example`,
`.github/workflows/ci.yml`, `frontend/package.json`, `frontend/next.config.ts` (CSP), `backend/app/modules/users/service.py` (export, deletion),
`frontend/src/components/layout/app-sidebar.tsx`, `backend/app/core/rate_limit.py`, `backend/app/ai/orchestration/*`, the Celery task registry.

## Preconditions
- [ ] Phase 3 merged, `docs/PHASE3_ACCEPTANCE.md` reviewed by a human, `main` green in CI.
- [ ] Retrieval quality checked on real lecture files (spec "How the phases connect": poor retrieval gives poor study material). Record the result; a weak result does not block Phase 4 but must be written down.
- [ ] `GEMINI_API_KEY` available locally only. Provider spending limit set; generation calls cost money.
- [ ] `docs/PHASE4_SPEC.md` in the repo.

## M0: Review Phase 3 and build the common generation engine (spec 25 steps 1 and 2; sections 3, 4, 17, 18.1 to 18.3, 21.1, 21.2, 21.6)
- [ ] Review Phase 3 and record in `docs/STUDY_GENERATION_ARCHITECTURE.md` what is reused: documents, chunks and provenance, retrieval, citations, ScopeResolver, Celery, provider layer, prompt registry, usage records, quotas. Deliverable: one reusable `SourceReader` interface (ordered read for chapters/documents, sampled or retrieved read for large scopes); nothing rebuilt.
- [ ] Decisions D-78+: SourceReader modes and map-reduce; one structured-output path with exactly one correction attempt; answer keys stored once and never returned before submission; no duplicated source content; regeneration is a preview/proposal and never overwrites edits; versioned snapshots; CSV formula-injection protection; per-user generation quotas and limits; duplicate-job prevention.
- [ ] Migration: `study_materials`, `study_material_versions`, `generation_jobs` (spec 18.1 to 18.3) with ownership constraints, indexes, `archived_at`; `ai_usage_records.request_kind` gains `generation`; user generation preferences (spec 16) in a dedicated table. One head, upgrade and downgrade tested.
- [ ] Generation engine: request schema, generator registry, per-generator validated settings, source selection via ScopeResolver (completed active versions only), context-size estimate, model selection, prompt registry entries, structured-output validation with Pydantic (required fields, types, array lengths, difficulty values, source references, duplicates).
- [ ] Jobs on Celery: statuses pending, retrieving sources, generating, validating, saving, completed, failed, cancelled; progress, timeouts, retry only for transient errors, generation ids, duplicate-job prevention, cancellation, safe error codes; do not auto-restart an expensive generation whose outcome is uncertain.
- [ ] Limits: max requests, max items per generator, max output tokens, per-user quotas, background job quotas, timeouts, usage tracking (spec 21.6).
- [ ] Tests (FakeProvider): lifecycle, cross-user 404, quota, invalid output then corrected, invalid twice fails safely, cancel, duplicate request returns the existing job, no content in logs. Regenerate OpenAPI and frontend types.
- Done when: a fake "echo" generator runs end to end through the engine with all of the above verified.

## M1: Summary generator (step 3; sections 5, 15.5, 22.1)
- [ ] Types: quick, detailed, section-wise, exam-oriented, beginner-friendly, key-point (5.2). Settings per 5.3, structure per 5.4.
- [ ] Whole-chapter summaries use ordered map-reduce so no part is silently skipped; the result reports which sources were included. Quality requirements 5.5.
- [ ] Source references validated like Phase 3 citations (invalid ones stripped).
- [ ] Edit and save; regenerate entire resource or selected section as a preview.
- [ ] Tests (spec 22.1): each type, attribution, coverage (every chunk reaches the reducer), empty or insufficient source, injection text inside a document not followed, ownership.

## M2: Flashcard generator (step 4; sections 6, 15.3, 22.2)
- [x] `flashcard_sets` and `flashcards` (18.4, 18.5). Card types: basic, definition, concept, comparison, fill-in-the-blank, application (6.2). Settings 6.3, schema 6.4.
- [x] Near-duplicate detection, quality rules 6.5, source reference per card.
- [x] Endpoints per 19.3: get set, add card, edit card, delete card; reorder; regenerate selected cards as a preview.
- [x] Tests (22.2): structure, duplicates, wording limits, references, editing, ownership, quotas.

## M3: Quiz generator and attempt engine (step 5; sections 7, 15.4, 19.4, 21.4, 22.3)
- [x] `quizzes`, `quiz_questions`, `quiz_attempts`, `quiz_attempt_answers` (18.6 to 18.9). Types: MCQ, multiple-select, true/false, fill-in-the-blank, short-answer, descriptive (7.2); difficulty (7.4).
- [x] Per-type validation of generated questions and answer keys (for example exactly one correct option for MCQ). Answer keys and explanations are never returned by any question endpoint before submission.
- [x] Attempts: start, save answers, submit (idempotent, no modification after submission), server-side timer, server-side grading for objective types, scores and per-question results (7.7, 7.8); retake behaviour defined and recorded.
- [x] Short-answer and descriptive questions: store the model answer and rubric; objective scoring only for objective types, subjective ones are self-assessed or flagged (record the decision).
- [x] Tests (22.3): generation per type, answer-key validation, scoring, result persistence, answer-key leakage sweep over every route and response schema, timer expiry, double submit, cross-user 404.

## M4: Study guides, glossaries, formula sheets, question banks (step 6; sections 8 to 11, 22.4 to 22.6)
- [x] Study guide (8): heading hierarchy, learning objectives, topic coverage, source attribution.
- [x] Glossary (9): term extraction, definitions, duplicate terms merged, source references, search.
- [x] Formula sheet (10): LaTeX validation, variable definitions, safe rendering, invalid formula handling (10.4).
- [x] Question bank (11): organisation by topic and difficulty (11.3), requirements 11.4; shares question validation with M3 without storing answer keys in public responses.
- [x] All use the M0 engine and registry; settings schemas, prompts (versioned) and tests per generator.

## M5: Study library, editing, versioning, regeneration and export (steps 7 and 8; sections 12 to 14, 16, 19.2, 19.5)
- [x] Library API (19.2): list with search, filters (type, workspace, subject, chapter, status), pagination and allow-listed sorts; get, patch, delete, duplicate, archive, regenerate.
- [x] Versioning (13.2): original generated version kept, current edited version, version number, modified by and when; restore. Regeneration always previews and never overwrites edits (13.3).
- [x] Preferences (16): language, explanation level, summary length, question difficulty, include examples/definitions/references; endpoints and use as generation defaults.
- [x] Export (14, 19.5): PDF and CSV first, then Markdown and DOCX where cheap; background job; short-lived, ownership-checked download; CSV cells starting with `=`, `+`, `-`, `@`, tab or CR neutralised; sanitised HTML/Markdown in PDF; quiz exports never contain answer keys unless the spec allows it after submission.
- [x] Account export and deletion cover all Phase 4 data; deleting a source document does not delete study materials but marks references unavailable.
- [x] Tests: filters, search, version restore, regenerate preview, export per resource type, injection payloads, expired or foreign download link, deletion cascade.

## M6: Frontend: generation, library, summaries, flashcards, guides (sections 20.x, 12.2)
- [x] Library gets a Study materials tab; entry points on subject, chapter and document pages; generation dialogs with scope, settings, quota hint; job progress with polling and cancel; failure states. (a Study materials page linked from the Library page tabs and the sidebar; entry points on subject, chapter and document pages)
- [x] Summary viewer and editor with source references, version history, regenerate-preview review; flashcard deck viewer, study mode, editing; study guide, glossary (search), formula sheet (safe LaTeX rendering) and question bank views.
- [x] Tests: Vitest and Playwright (Fake providers) covering generate, view, edit, regenerate preview, versions, isolation between users, mobile; accessibility and keyboard checks. (generate is covered to its failure state on the fake provider; regenerate preview and apply are not driven end to end because the fake provider cannot write study output: see GENERATION_SECURITY.md and STUDY_GENERATION_TESTING.md; keyboard and role checks yes, no axe audit)

## M7: Frontend: quizzes, results, exports, preferences (sections 7.6, 7.8, 14, 16, 20.x)
- [x] Quiz generation and list; quiz-taking screen with server-driven countdown, navigation, flagging, autosave, resume after refresh, auto-submit on expiry; results and review (explanations only after submit); attempt history.
- [x] Export buttons and download handling; preferences page.
- [x] Tests: Playwright full quiz, timer expiry, refresh-resume, assertion that no answer key appears in network responses before submit, isolation, mobile.

## M8: Usage controls, security review, evaluation, docs and acceptance (steps 9 and 10; sections 21, 22.7, 23, 26)
- [x] Security review (`docs/GENERATION_SECURITY.md`): ownership tests for every route, answer-key leakage sweep, prompt-injection, output sanitisation, quotas and cost limits, export injection, logs free of content, pip-audit and npm audit. (human items: live injection test, pip and npm audit rerun at release)
- [x] Evaluation (`docs/STUDY_GENERATION_TESTING.md`): validity, coverage, duplicate rate on the Fake provider; cost-capped live script (not run by automation); blank columns for human scoring; per-generator quality and cost on real lecture material by a human. (script and protocol done; live run and human scoring NOT done: HUMAN-NEEDED)
- [x] Reliability: worker crash mid-generation, duplicate job, retry, provider outage, large scope. (mapped to existing tests; killing a real worker container is a manual check)
- [x] Docs per spec 26: `STUDY_GENERATION_ARCHITECTURE.md`, `SUMMARY_GENERATION.md`, `FLASHCARD_GENERATION.md`, `QUIZ_GENERATION.md`, `STUDY_GUIDES.md`, `STUDY_LIBRARY.md`, `EXPORT_SYSTEM.md`, `GENERATION_SECURITY.md`, `STUDY_GENERATION_TESTING.md`; README and `WORKFLOW.md` updated.
- [x] `docs/PHASE4_ACCEPTANCE.md`: walk spec section 23 line by line, Met / Partly / Not met with evidence. (25 Met, 17 Partly, 0 Not met)

## Out of scope (spec section 24, do not start)
Advanced spaced repetition and FSRS, retention prediction, adaptive difficulty, learner mastery modelling, misconception detection, knowledge graphs, AI viva, audio summaries, podcasts, simulations, research-paper comparison, collaboration.
