# Assessment, retention and revision architecture (Phase 5)

Written in P5-0 (M0). Requirements: `PHASE5_SPEC.md`. Decisions: `DECISIONS.md` D-102 to D-114.
Phase 5 builds on Phase 4 and does not rebuild generation, retrieval, documents or the quiz engine.
This file is updated at M8 with what was actually built.

## 1. What Phase 4 already provides (reviewed in P5-0)

| Area | Existing | Where |
|---|---|---|
| Quizzes | `quizzes`, `quiz_questions` (answer key stored once, D-94), settings, `time_limit` | `models/quiz.py`, `modules/study/quiz_service.py` |
| Attempts | `quiz_attempts` (one open per quiz and user, server deadline, saved answers and review flags in JSONB, score, percentage, `auto_submitted`), `quiz_attempt_answers` (per-question result written at submit) | same |
| Grading | Objective types graded on the server (D-96); short answer and descriptive are `self_assessment`, excluded from the score | `study/quiz_grading.py` |
| Results | `GET /study/quizzes/{quiz}/results/{attempt}`, 409 until submitted; key only here | `quiz_routes.py` |
| Timer, resume, idempotent submit | D-95 (lazy finalisation, 10 s grace, row lock) | `quiz_service.py` |
| Flashcards | `flashcard_sets` (live deck) and `flashcards` (cards with `difficulty`, `source_references`, `revision`) | `models/flashcard.py`, `flashcard_service.py` |
| LLM access | Provider layer with `FakeProvider`, prompt registry (versioned, immutable), `ai_usage_records` (`request_kind`), daily token quota, rate limiter | `app/ai/`, `core/rate_limit.py` |
| Generation | One engine; quiz and flashcard generators write the rows above | `app/study/` |
| User timezone | `user_profiles.timezone` (IANA string, default `UTC`) | `models/user_profile.py` |
| Deletion | User delete cascades; flashcard and quiz FKs cascade; subject/chapter links use `SET NULL (col)` | models |

Gaps found (and what M0 did about each):

1. **No topic on questions or cards.** The question-bank generator invents a topic but it lives only in the material JSON. M0 adds `topic` to `quiz_questions` and `flashcards` and a version 2 of the `study_quiz` and `study_flashcards` prompts that ask for it (D-102). Old rows keep `topic = NULL`.
2. **Attempts lack counts, time taken, abandoned status, evaluation status and idempotency key.** Added (D-103).
3. **Answers lack grading method, maximum score, evaluation status.** Added (D-104). Phase 4 self-assessed rows are back-filled as `grading_method = self_assessment`, `max_score = 0`.
4. **Nothing models flashcard memory state.** New tables (D-106).
5. **`flashcards` had no `(id, user_id)` unique key**, so composite ownership FKs were impossible. Added (`uq_flashcards_id_user`).
6. **`ai_usage_records.request_kind` allows only `chat`, `embedding`, `generation`.** M1 adds `evaluation` with its own migration when descriptive grading is built (D-112). Not needed in M0.
7. **Attempt review marks** already exist as `quiz_attempts.flagged` (a JSONB list). Kept; no second column (spec 4.2 "review marks" is satisfied).

## 2. What Phase 5 adds

```
modules/revision/fsrs_scheduler.py   pure FSRS adapter (M0)              -> D-105, D-107
modules/revision/…                   revision service (M3)               -> sessions, due lists, review
modules/analytics/…                  derived analytics (M5)              -> D-108
modules/recommendations/…            rule-based recommendations (M6)
models/revision.py                   flashcard_scheduling, flashcard_reviews, revision_sessions,
                                     revision_recommendations (M0)
alembic 0009                         columns on quiz_*, flashcards + the four tables
```

Layering stays route -> service -> repository -> model. `FsrsScheduler` has no database, clock or random source: the service passes `now` and gets a new state back. LLM calls (descriptive grading M1, optional recommendation rewording M6) go only through the existing provider layer; scheduling and objective grading never call an LLM.

### Schema (migration 0009, one head)

| Table | Change | Key constraints and indexes |
|---|---|---|
| `quiz_questions` | + `topic` varchar(120) NULL | index `(user_id, topic)` |
| `flashcards` | + `topic` NULL; + unique `(id, user_id)` | target of composite FKs |
| `quiz_attempts` | status adds `abandoned`; + `correct_answers`, `incorrect_answers`, `unanswered`, `max_score`, `time_taken_seconds`, `abandoned_at`, `evaluation_status`, `submit_idempotency_key` | partial unique `(user_id, submit_idempotency_key)`; index `(user_id, submitted_at)`; check on status values |
| `quiz_attempt_answers` | + `max_score`, `grading_method`, `evaluation_status`, `ai_assisted`, `evaluation_detail` JSONB, `evaluation_error_code`, `evaluated_at` | checks on method and status; index `(user_id, question_id)` |
| `flashcard_scheduling` | new | unique `(user_id, flashcard_id)`; composite FK `(flashcard_id, user_id)` -> `flashcards(id, user_id)` CASCADE; indexes `(user_id, due_at)`, `(user_id, state)`, `flashcard_id` |
| `flashcard_reviews` | new, append-only | unique `(user_id, idempotency_key)`; composite FK to the card (CASCADE) and to `revision_sessions(id, user_id)` (`SET NULL (session_id)`); indexes `(user_id, reviewed_at)`, `(flashcard_id, reviewed_at)`, `session_id` |
| `revision_sessions` | new | unique `(id, user_id)`; partial unique one `active` per user; FK subject `SET NULL`, `(chapter_id, subject_id)` -> `chapters` `SET NULL (chapter_id)`; index `(user_id, started_at)` |
| `revision_recommendations` | new | partial unique `(user_id, dedupe_key)` while `pending`; index `(user_id, status, created_at)` |

`topic_performance` (spec 4.6) is **not** created (D-108).

Existing data: new columns are nullable or defaulted; counts, `max_score` and `time_taken_seconds` of already submitted attempts are back-filled from stored answers; `unanswered` stays NULL where it cannot be proven. Downgrade drops the four tables and the new columns; it also deletes `abandoned` attempts, which cannot exist in the old status set and hold no result. Tested with data in `tests/revision/test_migration_0009.py`.

## 3. Endpoint mapping (spec section 5 -> this application)

Rule: extend what exists, never add a second route for the same thing. Base path `/api/v1`. "New" means no equivalent exists. Milestones in brackets.

### 5.1 Quiz attempts

| Spec | Decision | Route in this app |
|---|---|---|
| `POST /quizzes/{id}/attempts` | **Reuse** (start or resume, D-95) | `POST /study/quizzes/{quiz_id}/attempts` |
| `GET /quiz-attempts` | **New**, because the existing list is per quiz only (cross-quiz history with filters, M1) | `GET /study/quiz-attempts` |
| `GET /quiz-attempts/{id}` | **Reuse** | `GET /study/quizzes/{quiz_id}/attempts/{attempt_id}` |
| `PUT /quiz-attempts/{id}/answers/{question}` | **Reuse** (the existing PUT saves a set of answers and the flag set; one question is a set of one) | `PUT /study/quizzes/{quiz_id}/attempts/{attempt_id}/answers` |
| `POST /quiz-attempts/{id}/submit` | **Reuse**, extended with optional idempotency key (D-109) | `POST …/attempts/{attempt_id}/submit` |
| `GET /quiz-attempts/{id}/results` | **Reuse**, extended with topic breakdown, AI-assisted fields (M1) | `GET /study/quizzes/{quiz_id}/results/{attempt_id}` |
| `GET /quizzes/{id}/attempts/history` | **Reuse**: the per-quiz list gains filters and comparison (M1) | `GET /study/quizzes/{quiz_id}/attempts` |
| (not in spec) abandon, mark for review, retry evaluation | **New** [M1] | `POST …/attempts/{attempt_id}/abandon`, `POST …/attempts/{attempt_id}/evaluation/retry`; review marks use the existing `flagged` field of the PUT |
| (not in spec) delete own attempt | **New** [M1] | `DELETE …/attempts/{attempt_id}` |

### 5.2 Flashcard scheduling

Flashcard routes already live under `/study/flashcards`; the review routes go with them. The `/revision/*` list routes are new because no revision concept exists.

| Spec | Decision | Route |
|---|---|---|
| `GET /revision/due`, `/new`, `/overdue`, `/summary` | **New** [M3] | same paths under `/revision` |
| `GET /flashcards/{id}/schedule` | **New** [M3] | `GET /study/flashcards/cards/{card_id}/schedule` |
| `POST /flashcards/{id}/review` | **New** [M3] | `POST /study/flashcards/cards/{card_id}/review` |
| `PATCH …/suspend`, `…/unsuspend` | **New** [M3] | `PATCH /study/flashcards/cards/{card_id}/suspend`, `/unsuspend` |
| `GET …/review-history` | **New** [M3] | `GET /study/flashcards/cards/{card_id}/review-history` |

(`/study/flashcards/cards/{card_id}` is the existing card PATCH/DELETE prefix; the schedule routes extend it.)

### 5.3 Revision sessions: all **New** [M3]

`POST/GET /revision/sessions`, `GET /revision/sessions/{id}`, `POST …/complete`, `POST …/abandon` exactly as in the spec.

### 5.4 Analytics: all **New** [M5]

`GET /analytics/overview`, `/quiz-performance`, `/subject-performance`, `/topic-performance`, `/revision-activity`, `/study-calendar`, `/streaks`, with filters `subject_id`, `chapter_id`, `start_date`, `end_date`.

### 5.5 Recommendations: all **New** [M6]

`GET /recommendations/revision`, `GET /recommendations/weak-topics`, `POST /recommendations/{id}/complete`, `POST /recommendations/{id}/dismiss`.

Every new route: authenticated, active account, owner-scoped query (join to `user_id`), 404 for foreign ids, Pydantic validation with allow-listed filters and capped limits, `{success, data}` envelope. The OpenAPI sweep tests from Phase 4 (`tests/study/test_route_sweep.py`) cover the new routes automatically; M8 adds the answer-key and ownership sweeps for them.

## 4. Data flow

**Quiz attempt (M1):** start/resume -> save answers (server stores; timer from the server) -> submit (row lock, idempotent) -> objective grading in one transaction -> descriptive answers queued for LLM grading with the stored rubric (status `pending`, never silently 0) -> results.

**Flashcard review (M3):** `POST review {rating, response_time_ms?, idempotency_key}` -> ownership check -> lock the scheduling row (created lazily if missing) -> `FsrsScheduler.review(state, rating, now)` -> update scheduling and insert the review event with previous and resulting state in one transaction -> return the new schedule. A repeated key returns the stored event.

**Analytics (M5):** SQL aggregates over attempts, answers and reviews, filtered by `user_id` and the user's timezone (D-108, D-111). No cron needed.

## 5. Security notes specific to Phase 5

- Answer keys (`correct_answers`, `explanation`, `rubric`) stay in `quiz_questions` and are returned only by the submitted-attempt results (D-94). Descriptive grading reads the key inside the service and returns only the grade, a short explanation and missing points that the grader model wrote.
- Student answers sent to the grader are untrusted data inside escaped markers; the grading rules live in the system prompt; output is validated by a Pydantic model and the score is clamped to `[0, max_score]` (D-112).
- Review and submit endpoints are rate-limited per user; descriptive grading also counts against the daily token quota.
- Logs carry ids, counts, ratings, scores and durations only; never answers, card text or model output.
- `recommendation.target_id` has no FK, so reading it re-checks ownership of the target and skips targets that were deleted.
