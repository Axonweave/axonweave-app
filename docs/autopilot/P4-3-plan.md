# P4-3 plan - Quiz generator and attempt engine (backend only)

1. Migration 0007: `quizzes`, `quiz_questions` (answer key + rubric, only place keys live), `quiz_attempts`, `quiz_attempt_answers`; composite owner FKs, grants.
2. Generator `quiz` on the M0 engine (prompt `study_quiz` v1): six question types, per-type answer-key validation, near-duplicate and leakage checks, source refs. The material payload is stripped of keys (`dump` returns title and counts only), so `/study/materials/*` never exposes them.
3. Quiz routes `/study/quizzes`: get quiz (no keys), start/resume attempt, get attempt, save answers, submit (idempotent, row-locked), results (only after submission), attempt history.
4. Server-side timer (deadline from `started_at`, lazy auto-submit on expiry), exact-match grading for objective types, subjective types not auto-graded (recorded decision).
5. Tests: generation per type, key validation, scoring, persistence, timer expiry, double submit, 404 cross-user, answer-key leakage sweep over every route and schema.
6. Decisions D-94.. in DECISIONS.md, AUTOPILOT_LOG lines, tick M3, final PR description.
