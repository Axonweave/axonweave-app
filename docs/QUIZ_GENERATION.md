# Quiz generation, taking and scoring (Phase 4)

Requirements: `PHASE4_SPEC.md` section 7. Decisions: D-94 (answer key), D-95 (retakes and timer), D-96 (scoring), D-99 (question bank). Code: `app/study/generators/quiz.py`, `app/study/quiz_grading.py`, `app/modules/study/quiz_service.py`, `quiz_routes.py`, `quiz_schemas.py`; prompt `study_quiz`.

## Settings (`generation_type: "quiz"`)
`count` 1 to 50 (default 10); `question_types` any of `multiple_choice`, `multiple_select`, `true_false`, `fill_in_the_blank`, `short_answer`, `descriptive`; `difficulty` easy, medium, hard or mixed; `time_limit_minutes` 1 to 300 or none; `randomize_order`; `show_explanations` accepts only `after_submission`.

## Per-type rules (validated; a violation gets one correction call, then the job fails)
- Multiple choice: 3 to 6 options (ids A to F), exactly one correct id.
- Multiple select: 4 to 6 options, two or more correct but not all.
- True/false: fixed options `true` and `false`.
- Fill in the blank: exactly one `___`, short accepted answers that the question does not contain.
- Short answer: one model answer and 1 to 6 rubric points. Descriptive: one model answer and 2 to 8 points.
- Questions with no valid source are dropped; near-duplicates fail validation.

## The answer key
`correct_answers`, `explanation` and `rubric` are stored once, in `quiz_questions`. The material content holds only title and counts. Pre-submission schemas (`QuizOut`, `QuizQuestionOut`, `AttemptOut`, `AttemptListOut`) have NO key fields; only `ResultQuestionOut`, returned by `GET .../results/{attempt_id}` of a submitted attempt, has them (409 `QUIZ_ATTEMPT_NOT_SUBMITTED` before). Tests walk every OpenAPI response schema and every GET, and the Playwright quiz test asserts no response the browser received before submit contains a key word.

## Attempts
`POST /study/quizzes/{id}/attempts` starts an attempt, or returns the open one (resume after a refresh). At most one attempt is open per quiz and user; retakes are unlimited up to 100 per quiz and each has a fresh question order. `PUT .../answers` autosaves (answers and the flagged set), `POST .../submit` finishes, `GET .../results/{attempt_id}` returns the review. Submit is idempotent and row-locked; saving after submit is 409 `QUIZ_ATTEMPT_SUBMITTED`.

## Timer
The deadline is `started_at + time_limit`, computed and enforced on the server. Responses carry `server_time` and `seconds_remaining`; the browser countdown only displays that. An expired attempt is finalised lazily with the answers saved before the deadline (`auto_submitted`), saving after the deadline is 409 `QUIZ_ATTEMPT_EXPIRED`, and a submit gets 10 seconds of grace in which its own body counts. The quiz page submits when the countdown reaches zero and shows "submitted automatically".

## Scoring (D-96)
One point per objective question; multiple select is exact match (no partial credit); fill-in-the-blank compares NFKC, case-folded, whitespace-collapsed text with edge punctuation removed against the accepted answers. Short-answer and descriptive questions are `self_assessment`: not graded by the server or a model, excluded from score and percentage, shown with the model answer and rubric. `percentage` is null when there are no objective questions. Results always say a quiz score is not a measure of overall mastery (spec 7.8).

## Question bank (D-99)
Generated with `generation_type: "question_bank"`; reuses the quiz validation and tables (untimed). The material shows the public view (no keys). A bank can be practised as a quiz at `/study/{id}/quiz`.

## UI
`/study/{id}` (quiz facts, attempt history), `/study/{id}/quiz` (navigation, answer controls, flag, progress, countdown, autosave state, submit confirmation with unanswered count), `/study/{id}/quiz/results/{attempt}` (score, per-question review, explanations).

## Tests
`backend/tests/study/test_quiz.py` (types, keys, scoring, timer, expiry, double submit, leakage sweep); `frontend/src/features/study/study.test.tsx` (resume, autosave, flags, confirm, auto-submit); `frontend/e2e/study.spec.ts` (full quiz, refresh-resume, key sweep, timed expiry).
