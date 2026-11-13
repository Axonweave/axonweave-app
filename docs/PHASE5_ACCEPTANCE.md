# Phase 5 acceptance: Assessment, Retention and Revision Intelligence

Walks `PHASE5_SPEC.md` section 10 line by line. Status values: **Met**, **Partly**, **Not met**.
"Verified" means an automated test ran green in this branch; anything that needs a human or a live
provider says so. Decisions: D-102 to D-120 in `DECISIONS.md`.

| # | Criterion | Status | Evidence and gaps |
|---|---|---|---|
| 1 | Users can start and submit quizzes created in Phase 4 | Met | Phase 4 quiz tests plus `tests/study/test_quiz_assessment.py` (start, resume, idempotent submit). The quiz-taking UI is the Phase 4 one. |
| 2 | Attempts are saved and can be reviewed later | Met | Attempts persist; results and review via `GET .../attempts/{id}/results` and the results page. |
| 3 | Objective questions graded correctly on the backend | Met | Server-side grading unchanged from Phase 4 (99 tests) and re-verified in M1 tests. |
| 4 | Descriptive questions can receive AI-assisted feedback | Met on the fake provider; Not verified live | Grading, retry and failure paths tested with `FakeProvider`. No live provider call was made, so real-model grading quality is **HUMAN-NEEDED**. |
| 5 | Results show scores and topic-wise performance | Met | `topic_performance` and suggested topics in the results API; shown in the results page. |
| 6 | Users can review their quiz history | Met | API tests plus the `/study/history` page (status and date filters, pagination, results links, two-attempt comparison). Filters: subject, chapter, status and date range (the end date includes the whole day). Verified in the browser by `e2e/revision.spec.ts`; the filter component has Vitest tests. |
| 7 | Users can access Phase 4 flashcards | Met | They appear in `/revision` once scheduled lazily. |
| 8 | FSRS schedules reviews from ratings | Met | py-fsrs 6.3.2 behind `fsrs_scheduler.py`; adapter and API tests. |
| 9 | Users can complete revision sessions | Met | Session API tests (44) and the session runner UI (Vitest, keyboard shortcuts). `e2e/revision.spec.ts` runs a 3-card session with the keyboard to completion in a browser. |
| 10 | Due, new and overdue shown correctly | Met | Revision API tests including timezones; Revision Centre shows the counts. |
| 11 | Review history is persisted | Met | Append-only `flashcard_reviews`, `review-history` endpoint. |
| 12 | Subject-wise and topic-wise performance | Met | `/analytics/subject-performance` and `/topic-performance` tested. The progress page now shows both a subject table and the topic table. |
| 13 | Weak topics identified from assessment evidence | Met | Rule-based, thresholds returned with the data (D-117). |
| 14 | Basic personalised recommendations | Met | Rule engine, dedupe and dismissal tested (D-119). No LLM wording (D-120). |
| 15 | Analytics and study calendar correct | Met | 16 analytics tests (empty account, filters, ranges, isolation). The progress page has subject, chapter and date filters, a calendar grid with day details, a quiz-score trend and a cards-per-day chart (hand-written SVG, D-121). The browser test checks the calendar cell against the real attempts and reviews. Large-data check: `scripts/analytics_load_check.py` on 3000 attempts and 30000 answers gave 11 to 224 ms per query over three runs (see below for one slow first run). |
| 16 | All user data protected by ownership checks | Met | Every repository query filters by `user_id`; cross-user tests in the quiz, revision, analytics and recommendation suites return 404 or empty. |
| 17 | Errors, retries, duplicate requests handled | Met | Idempotency keys on submit and review, concurrent submit/review tests, grading failure leaves `pending`. |
| 18 | Phase 1 to 4 keep working | Met | Full backend suite: 1346 passed, 41 skipped, 0 failed. Full backend suite: 1346 passed, 41 skipped, 0 failed. Frontend Vitest: 271 passed. Full Playwright suite (all 9 spec files, desktop and phone): **137 passed, 53 skipped by design, 0 failed**, run in one go with the documented e2e configuration (below). |

## Not built or not verified
- Quiz taker: review marks and resume already existed from Phase 4 and were not changed; M2 only extended the results screen.
- Per-user retention setting and parameter optimiser. Left out on purpose (D-107, D-120); the spec asks for it only if the FSRS library supports it.
- Live-provider grading, and visual, mobile and accessibility review by a person. The phone Playwright check only tests for sideways scrolling.
- Calendar days and history dates use UTC day boundaries for the date filters on the history page; the analytics endpoints use the user's own timezone.

## Load check notes
`docker compose exec -T backend python scripts/analytics_load_check.py <email> 3000` seeds attempts for one user, times each analytics method and the history query, and removes the data. Three runs: every query 11 to 224 ms (overview 155 to 224 ms, topic-performance 69 to 111 ms, history page 31 to 38 ms). **The very first run reported a slowest query of about 42 seconds.** I did not identify which query it was, and it did not recur in three later runs. A likely cause is stale planner statistics straight after a bulk insert, but that is a guess. Treat analytics on a freshly bulk-loaded database as unproven until it is looked at again.

## Running the browser tests
- The browser specs expect the stack in the configuration from `docs/SETUP.md`: `LLM_PROVIDER=fake LLM_DEFAULT_MODEL= FAKE_LLM_CHUNK_DELAY_SECONDS=0.1 TRUST_PROXY_HEADERS=true`. Without `TRUST_PROXY_HEADERS` the specs' spoofed IPs are ignored and every registration counts against one IP (10 per 15 minutes, 10 verifications per hour), so a second run in a row fails with "Too many requests". Clear the `rl:*` keys in the dev Redis between runs.
- Without `LLM_PROVIDER=fake` the AI Tutor spec fails at its first step (the privacy notice names the real provider).
- The `frontend` container serves a build made at image build time. Rebuild it (`docker compose up -d --build frontend`) before Playwright, or new pages return 404.
- One run showed a single failure in `library.spec.ts` ("the sidebar opens the Library, which starts empty") under four parallel workers. It passed on every rerun, alone and in the next full run. Treat it as a timing flake, not a fixed bug.

## Security notes
- Answer keys stay behind submit: results route only; the sweep tests from Phase 4 still pass.
- Student answers are passed to the grader as escaped data inside markers; instructions inside an answer do not change grading rules (injection test).
- No message content or answers are logged; usage rows carry ids, model, token counts only.
- Analytics, revision and recommendation routes require login and CSRF for writes (POST/PATCH).
