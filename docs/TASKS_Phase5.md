# Task board and ownership (Phase 5: Assessment, Retention and Revision Intelligence)

Requirements: `PHASE5_SPEC.md` (sections 1 to 15). Decisions: `DECISIONS.md` from the next free number (written by M0). Autopilot prompts: `docs/prompts/P5-*.md`.
Tick a task only when its PR is merged to `main`. One branch per task, Conventional Commits, no push to `main`, one Alembic head.
Every milestone ends with ruff, mypy, pytest, Vitest (and Playwright from the UI milestones) green. Phase 5 builds on Phases 1 to 4: do not rebuild generation, retrieval, documents or the quiz engine (spec sections 7 and 14).

## Overlap with Phase 4 (read first)
Phase 4 M3/M7 already created `quizzes`, `quiz_questions`, `quiz_attempts`, `quiz_attempt_answers`, server-side timer, grading of objective types, results and a quiz-taking UI; `flashcards` and `flashcard_sets` exist from M2. Spec section 4 lists tables with the same names. Rule: inspect first, then EXTEND existing tables and routes with new columns/endpoints, never create a second table or a second route for the same thing. Differences are recorded in DECISIONS.md.

## Shared files (change minimally, mention in the PR)
`backend/app/api/v1/router.py`, `backend/app/main.py`, `backend/app/models/__init__.py`, `backend/requirements.txt`, `docker-compose.yml`, `.env.example`,
`.github/workflows/ci.yml`, `frontend/package.json`, `frontend/src/components/layout/app-sidebar.tsx`, `backend/app/modules/users/service.py` (export, deletion),
`backend/app/core/rate_limit.py`, the dashboard page, the Celery task registry.

## Preconditions
- [ ] Phase 4 merged, `docs/PHASE4_ACCEPTANCE.md` reviewed by a human, `main` green in CI.
- [ ] A human has generated real flashcards and quizzes from real lecture files and checked they are usable (Phase 5 evaluates the user's performance on them).
- [ ] `docs/PHASE5_SPEC.md` in the repo (product name replaced with Axonweave).
- [ ] `GEMINI_API_KEY` local only; descriptive grading costs money, so quotas stay on.

## M0: Review Phase 4, reconcile the schema, pick FSRS (spec 4, 7, 11 step 1, 13; sections 2.3, 8)
- [ ] Review the Phase 4 quiz, flashcard, attempt, usage and quota code. Write `docs/ASSESSMENT_ARCHITECTURE.md`: what is reused, what is added, and a table mapping every spec 5.x endpoint to the existing route or the new one (no duplicate routes).
- [ ] Decisions: FSRS library (choose a maintained Python FSRS implementation such as py-fsrs after checking its current version, license and API; pin it; record why); where review state lives; topic source for questions (use the existing topic field or add one to `quiz_questions` and flashcards through a migration and a versioned generation prompt change); derived aggregates first, stored aggregates only with a measured need and a recalculation job; user timezone for streaks and "today"; descriptive-grading rules (rubric from the stored model answer, structured output, AI-assisted label, grading failure shows "evaluation pending" and is retryable, never silently 0); idempotency-key approach for submit and review; retention (account deletion removes all Phase 5 data; deleting a flashcard removes its scheduling and keeps anonymised counts out of scope).
- [ ] Migration(s): extend `quiz_attempts`/`quiz_attempt_answers` with missing spec 4.1/4.2 columns (status values, counts, time taken, review marks, evaluation status, idempotency key); add `flashcard_scheduling` (unique `(user_id, flashcard_id)`), `flashcard_reviews` (with idempotency key), `revision_sessions`, `revision_recommendations`; indexes on `user_id`, `due_at`, timestamps; all ownership constraints. One head, upgrade and downgrade tested, existing data preserved.
- [ ] `FsrsScheduler` service: a thin adapter around the chosen library, pure (state + rating + now -> new state), target retention configurable, parameters stored with a version, deterministic. Tests against the library's own reference behaviour and fixed vectors.
- Done when: schema migrated and tested, scheduler unit-tested, architecture doc and decisions written, Phase 1 to 4 suites unchanged and green.

## M1: Quiz assessment backend (spec 2.1, 2.2, 5.1, 8; order steps 2, 3, 5)
- [ ] Attempt lifecycle on the existing routes/tables: start (one active attempt per quiz and user, or resume), save answer, change answer before submit, mark for review, resume, abandon, idempotent submit (a retry returns the same result), no edits after submit.
- [ ] Objective grading on the server for MCQ, multiple-select, true/false, fill-in-the-blank; unanswered handling; counts, score, percentage, time taken; transactions.
- [ ] Descriptive and short-answer grading by LLM through the existing provider layer: rubric and reference answer from the stored key, structured output with one correction attempt, indicative score with explanation, missing points, clear "AI-assisted" flag, rate limits and quota, failure becomes "evaluation pending" with a retry endpoint. Prompt injection inside the student's answer must not change the grade rules.
- [ ] Results API: totals, correct/incorrect/unanswered, score, percentage, time, per-question feedback and explanations, topic-wise performance for the attempt, suggested revision topics (derived, rule-based). Answer keys only after submit.
- [ ] History: list with filters (subject, chapter, quiz, dates), per-quiz history, compare attempts with improvement/decline, delete own attempts (what happens to derived stats recorded in DECISIONS).
- [ ] Tests (spec 9 quiz list): every item, plus answer-key leakage sweep over all routes, cross-user 404, duplicate submit, concurrent submit, descriptive grading failure and retry, injection in answers.

## M2: Quiz assessment frontend (spec 2.1, 2.2, 6; order steps 4, 5)
- [ ] Extend the Phase 4 quiz UI: one-at-a-time or all-questions view, navigation, review markers, timer where applicable, autosave through the backend, resume after refresh or network loss, submit confirmation, duplicate-click protection.
- [ ] Results page (all spec 2.1 fields, per-question feedback, AI-assisted label with an explanation, topic-wise chart); history page with filters and attempt comparison that does not claim a higher score proves retention.
- [ ] Tests: Vitest and Playwright (Fake providers): take, save, resume, review marks, submit, results, history, compare; no answer key in network responses before submit; isolation; mobile; accessibility. HUMAN-NEEDED: visual check.

## M3: Spaced repetition backend (spec 2.3, 2.5, 5.2, 5.3; order steps 6, 7)
- [ ] Scheduling records created lazily for each user's existing flashcards (and when new cards appear); new, learning, review and relearning states per the library.
- [ ] Endpoints: due, new, overdue, summary, schedule, review (idempotent; validates ownership; transaction updates scheduling and inserts the review event with previous and resulting state), suspend/unsuspend, review history, filters by subject and chapter. Early reviews and missed reviews handled. Time stored in UTC; "due today" uses the user's timezone.
- [ ] Revision sessions: start (card selection with limits, new-card cap), list, get, complete, abandon, stale-session handling, auto-save of results.
- [ ] Parameter changes preserve history; deleted flashcards remove scheduling safely.
- [ ] Tests (spec 9 FSRS list): all ratings, due dates, overdue, early, suspend, repeated and retried reviews, timezone boundaries, invalid or missing state, cross-user 404, concurrency on the same card.

## M4: Revision Centre and session UI (spec 2.4, 2.5, 6; order step 8)
- [ ] Revision Centre dashboard: due today, overdue, new, reviewed today, daily completion, upcoming schedule, recent activity, subject-wise status, filters (subject, chapter, due, overdue, new, suspended); sidebar entry.
- [ ] Session screen: question, reveal, Again/Hard/Good/Easy with keyboard shortcuts, source info, progress, end session, automatic saving, end-of-session summary (counts, rating distribution, time, next reviews). Handle offline/failed requests without double-submitting a rating.
- [ ] Tests: Vitest and Playwright (reveal, rate, progress, end, summary, failed request retry), isolation, mobile, a11y. HUMAN-NEEDED: visual check.

## M5: Topic performance and learning analytics backend (spec 2.6, 3, 5.4; order steps 9, 10)
- [ ] Topic performance computed from attempt answers (derived queries or a stored aggregate that can be fully recalculated); configurable thresholds for Strong / Developing / Needs revision with wording that does not claim mastery.
- [ ] Analytics endpoints: overview, quiz performance over time, subject performance, topic performance, revision activity, rating distribution, study calendar, streaks (current and longest, timezone-correct, no punishment for gaps); filters subject, chapter, start and end date; indexes and a measured performance check on seeded data.
- [ ] Tests (spec 9 analytics list): accuracy, averages, subject and topic breakdowns, completion, streaks across timezones and DST, date filters, strict per-user isolation, empty data.

## M6: Weak-topic detection and recommendations (spec 2.7, 2.8, 5.5; order steps 11, 12)
- [ ] Rule-based weak-topic detection from the signals in 2.7 with an explanation string built from real numbers; wording is "may need revision", never a verdict.
- [ ] Recommendation engine with the priority order from 2.8; recommendations stored with a reason and priority, deduplicated while pending, complete/dismiss endpoints, regenerated on demand or after relevant events. An optional LLM rewrite of the explanation receives only the computed facts and its output is validated to contain no new numbers; the app works fully without it.
- [ ] Tests: each signal, priority ordering, dedupe, complete/dismiss, explanation contains only real values, LLM off and on, cross-user isolation.

## M7: Analytics, calendar and recommendations UI (spec 3, 2.8, 6; order steps 10 to 12)
- [ ] Dashboard additions (overall stats, topics needing attention), Learning Analytics pages (performance overview, subject analytics, topic performance), charts with date, subject and chapter filters, study calendar with day drill-down and streaks, recommendations panel with complete/dismiss; loading, empty and error states; clear labelling of estimates versus facts. Reuse the existing design system and chart library.
- [ ] Tests: Vitest and Playwright (charts show backend data, filters, calendar drill-down, recommendations actions), isolation, mobile, a11y. HUMAN-NEEDED: visual check.

## M8: Testing, security, reliability, docs and acceptance (spec 8, 9, 10, 13; order step 13)
- [ ] Security review in `docs/ASSESSMENT_SECURITY.md`: ownership tests for every new route (OpenAPI walk), unauthenticated sweep, answer-key leakage sweep, rate limits on descriptive grading and review submission, idempotency, no content in logs, input validation, pip-audit and npm audit.
- [ ] Reliability: duplicate submits and reviews, concurrent requests, worker or provider outage during descriptive grading, session recovery, DB transaction failure paths. Regression: Phase 1 to 4 suites and e2e still green.
- [ ] Docs: `ASSESSMENT_ARCHITECTURE.md` (update), `QUIZ_ASSESSMENT.md`, `SPACED_REPETITION.md`, `LEARNING_ANALYTICS.md`, `ASSESSMENT_SECURITY.md`, README and `WORKFLOW.md` updated.
- [ ] `docs/PHASE5_ACCEPTANCE.md`: walk spec section 10 line by line, Met / Partly / Not met with evidence. Anything needing real study data over weeks, the live key or visual checks is at best Partly.

## Out of scope (spec section 12, do not start)
Knowledge graph, concept relationship extraction, prerequisite mapping, learner knowledge modelling, misconception detection, adaptive learning paths, research features, AI viva, simulations, audio revision, multilingual learning.


## Status (branch `phase5/complete`, one stacked PR)
Built: M1 quiz assessment backend, M3 spaced repetition backend (FSRS), M5 analytics backend, M6 recommendations backend, results-screen extension (M2 part), Revision Centre, session runner and Progress page (M4, M7 part). Not built: quiz history/compare pages, review-marks UI beyond Phase 4, Playwright tests, dashboard additions. See `PHASE5_ACCEPTANCE.md` for the line-by-line status. Nothing here is ticked as merged; tick tasks when the PR is merged.
