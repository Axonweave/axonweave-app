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
| 6 | Users can review their quiz history | Partly | API: `GET /study/quiz-attempts` with filters, per-quiz history and compare (tested). **No history or compare page in the browser.** |
| 7 | Users can access Phase 4 flashcards | Met | They appear in `/revision` once scheduled lazily. |
| 8 | FSRS schedules reviews from ratings | Met | py-fsrs 6.3.2 behind `fsrs_scheduler.py`; adapter and API tests. |
| 9 | Users can complete revision sessions | Met | Session API tests (44) and the session runner UI (Vitest, keyboard shortcuts). No Playwright run. |
| 10 | Due, new and overdue shown correctly | Met | Revision API tests including timezones; Revision Centre shows the counts. |
| 11 | Review history is persisted | Met | Append-only `flashcard_reviews`, `review-history` endpoint. |
| 12 | Subject-wise and topic-wise performance | Met (API) / Partly (UI) | `/analytics/subject-performance` and `/topic-performance` tested. UI shows the topic table only; no subject breakdown view. |
| 13 | Weak topics identified from assessment evidence | Met | Rule-based, thresholds returned with the data (D-117). |
| 14 | Basic personalised recommendations | Met | Rule engine, dedupe and dismissal tested (D-119). No LLM wording (D-120). |
| 15 | Analytics and study calendar correct | Met (API) / Partly (UI) | 16 analytics tests (empty account, filters, ranges, isolation). The calendar is a list of days, not a grid; no charts. A performance check on large seeded data was **not** run. |
| 16 | All user data protected by ownership checks | Met | Every repository query filters by `user_id`; cross-user tests in the quiz, revision, analytics and recommendation suites return 404 or empty. |
| 17 | Errors, retries, duplicate requests handled | Met | Idempotency keys on submit and review, concurrent submit/review tests, grading failure leaves `pending`. |
| 18 | Phase 1 to 4 keep working | See test results below | |

## Not built or not verified
- Browser pages for quiz history and attempt comparison; a subject-performance view; charts.
- Quiz taker changes (review marks, resume) beyond what Phase 4 already had; M2 only extended the results screen.
- Playwright tests for any Phase 5 page. Vitest covers the session runner, helpers and topic table.
- Per-user retention setting; optimiser (D-107, D-120).
- Dashboard additions (due-today widget and streak on the dashboard page).
- Live-provider grading and visual/mobile/accessibility review by a person.
- Load test of analytics on thousands of attempts.

## Security notes
- Answer keys stay behind submit: results route only; the sweep tests from Phase 4 still pass.
- Student answers are passed to the grader as escaped data inside markers; instructions inside an answer do not change grading rules (injection test).
- No message content or answers are logged; usage rows carry ids, model, token counts only.
- Analytics, revision and recommendation routes require login and CSRF for writes (POST/PATCH).
