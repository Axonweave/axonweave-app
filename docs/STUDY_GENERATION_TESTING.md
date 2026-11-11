# Study generation testing and evaluation (Phase 4, M8)

Requirements: `PHASE4_SPEC.md` sections 15, 22 and 25 step 10. Automation here uses the FakeProvider and generated fixtures only: no network, no key, no cost. Anything about real model quality needs a person (section 4).

## 1. Automated test map
| Layer | Where | Covers |
|---|---|---|
| Backend generation (pytest) | `backend/tests/study/test_generation_flow.py` | engine, quotas, limits, duplicates, retry, timeout, cancel, stale jobs, logs |
| | `test_summary.py` | 22.1: all six types, references, coverage, map-reduce, injection, versions, regeneration |
| | `test_flashcards.py` | 22.2: structure, duplicates, references, editing, persistence |
| | `test_quiz.py` | 22.3: every question type, keys, scoring, persistence, timer, leakage sweep |
| | `test_guides_banks.py` | 22.4 to 22.6 and question banks: hierarchy, objectives, terms, search, LaTeX, invalid formulas |
| | `test_library_export.py` | library, versions, preferences, exports, injection payloads, account export and deletion |
| | `test_route_sweep.py` | every study route requires a login (read from the app, so new routes are covered) |
| Frontend unit (Vitest) | `frontend/src/features/study/study.test.tsx` | generation settings, safe LaTeX, formula warning, source references, editor, export formats, flashcard study mode, quiz taker (resume, autosave, flags, confirm, auto-submit) |
| End to end (Playwright) | `frontend/e2e/study.spec.ts` | list and filter, edit and versions, glossary search, formula rendering, flashcards by keyboard, full quiz with refresh-resume and an answer-key sweep of every network response, timed auto-submit, CSV export through the worker, preferences, second-user isolation, mobile layout |

Run: `docker compose exec backend pytest tests/study` (one pytest at a time), `cd frontend && npm run test`, `PW_EXTERNAL_STACK=1 npx playwright test e2e/study.spec.ts` (needs the stack up and `docker compose` on the same machine, because the test seeds materials with `backend/scripts/seed_study_e2e.py`). The test that drives a generation to its failure state runs only when `LLM_PROVIDER=fake`, so it can never call a real provider.

Why the browser tests seed materials: the FakeProvider cannot write structured study output. `seed_study_e2e.py` builds generated-style materials directly (development and testing environments only) so the viewers, editing, quiz and export can be tested end to end. It is not a way around validation: the same shapes are validated by the backend tests.

## 2. Reliability (M8) and where it is proven
| Scenario | Behaviour | Test |
|---|---|---|
| Worker dies mid-generation | The job is left to `study.sweep_stale_jobs`, failed with `GENERATION_INTERRUPTED`, never restarted (an expensive run of unknown outcome) | `test_stale_running_jobs_are_failed_never_restarted` |
| Duplicate or redelivered message | Atomic claim; second delivery does nothing | `test_redelivered_job_is_not_restarted` |
| Duplicate request | Returns the active job, `existing: true` | `test_identical_active_request_returns_the_existing_job` |
| Committed but never delivered | Re-sent by `study.dispatch_pending` | `test_undelivered_pending_jobs_are_found` |
| Provider transient error | Retried up to `STUDY_PROVIDER_MAX_RETRIES`; a timeout is never retried | `test_transient_error_is_retried_once`, `test_retries_are_limited`, `test_timeout_is_never_retried` |
| Provider outage or not configured | 503 `LLM_NOT_CONFIGURED` or a safe failure code; the rest of the app keeps working | `test_not_configured_and_no_broker`, retry tests |
| Invalid model output | One correction call, then `GENERATION_INVALID_OUTPUT` | `test_invalid_output_is_corrected_once`, `test_invalid_twice_fails_safely` |
| Large scope | Summaries map-reduce up to 30 batches; others sample and report `truncated`; too large is refused up front | `test_every_chunk_reaches_a_map_step_and_the_reducer_sees_every_batch`, `test_large_scope_is_sampled_and_reports_truncation`, `test_too_large_scope_is_refused_up_front` |
| Cancel | Pending cancelled at once; running cancelled mid-call; nothing saved | `test_pending_job_is_cancelled_at_once_and_never_runs`, `test_running_job_is_cancelled_while_the_provider_works` |
| Job timeout | Safe code, usage row recorded | `test_job_timeout_fails_with_a_safe_code` |
Not exercised here: a real Celery worker being killed with `docker kill` during a live provider call. The sweeper logic is tested directly; killing a container is a manual check (section 4).

## 3. Quality evaluation
### 3.1 What a script can measure
`backend/scripts/eval_study_generation.py` is read only (no model call). Run it after generating materials (on the FakeProvider in development, or through the app with the live provider):

```
docker compose exec -T backend python scripts/eval_study_generation.py <email> --out /app/study_eval.csv
docker compose cp backend:/app/study_eval.csv docs/ai_eval/results/study_eval.csv
```
It prints, per job type, jobs, validity (completed over finished), average provider calls, average duration and error codes; and writes per material: items, items with a valid source reference, reference coverage, invalid references, duplicate count and rate, formulas flagged. Counts only; no content is written.

On the FakeProvider these numbers measure the pipeline (the shapes are scripted), not model quality. Example run on the seeded Playwright fixtures: 7 materials measured, formula sheet 1 of 2 flagged, duplicate rate 0 everywhere. This proves the measurement works.

### 3.2 Cost
Run the generations through the app; it enforces its own caps (20 jobs a day, 2 at once, 10 a minute, output token cap per generator, daily token quota). That is the cost limit for live evaluation, so there is one set of limits and no second code path that could exceed them. Read tokens and cost from the usage page (`GET /api/v1/ai/usage/summary`); unknown cost is NULL, never 0. A `STUDY_DAILY_GENERATION_QUOTA` of 10 is a sensible cap for an evaluation day.

## 4. Human evaluation (not run by automation)
Needs the live provider key and real lecture material. Use 2 or 3 real documents (kept in `testdata-private/`, never committed): one text-heavy, one with formulas, one slide deck.
1. Upload and wait for Ready. Generate each type once from a chapter: summary (each of the 6 types), flashcards (10), quiz (10 mixed), study guide, glossary, formula sheet, question bank.
2. Run the script above and attach the CSV.
3. Score each material 1 to 5 in the empty columns, using this guide:

| Column | Question to answer |
|---|---|
| correctness | Is everything stated true according to the source? Check at least five items against the page cited. |
| coverage | Are the important topics of the source present? Is anything big missing? |
| clarity | Is it understandable and well worded? Are cards one concept each? |
| usefulness | Would you study from it? |
| reviewer_notes | Wrong or unsupported items (ids), duplicate cards, bad distractors. |

4. For quizzes also check: the answer key is right for every question; wrong options are plausible; each question is answerable from the source.
5. For formula sheets check every formula against the source and mark any the sheet flagged and any it did not but should have.
6. Cost per generator: note tokens and cost from the usage page before and after each run.
7. Manual reliability check: start a long summary and `docker compose kill worker` mid-run; within `STUDY_STALE_JOB_SECONDS` the job must become failed with `GENERATION_INTERRUPTED`, and the quota must not double count.
8. Visual and accessibility pass in a browser: desktop and phone widths, dark mode, keyboard only, a screen reader on the quiz and flashcard pages, contrast of the status chips.

Record results in `docs/ai_eval/results/` (not in git if they contain document content).

## 5. Known gaps
No automated colour-contrast or screen-reader test (Vitest and Playwright check roles, labels and keyboard only); no live-provider run; PDF and DOCX renderer tests skip in the API image; Playwright runs against whatever provider the stack has, so the generate-to-failure case only runs with `LLM_PROVIDER=fake`.
