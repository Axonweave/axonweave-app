# Study guides, glossaries, formula sheets and question banks (Phase 4)

Requirements: `PHASE4_SPEC.md` sections 8 to 11. Decisions: D-97, D-98, D-99. All four use the common `POST /study/generations`; there are no per-type routes except read-only search and filter.

## Study guide (`study_guide`)
Settings: `level` beginner, intermediate or advanced; `focus` exam_preparation, conceptual_understanding or practical_application; `max_sections` 3 to 40; toggles for objectives, prerequisites, examples, practice questions, source references.
Output: `title`, `overview`, `learning_objectives` (text, `generated_recommendation`, refs), `prerequisites`, `sections` (heading, `level` 1 to 3, body, bullets, refs), `key_takeaways`, `practice_questions` (question, refs).
Rules: heading levels must not skip (a skipped level fails validation); an objective with no source is kept only if flagged `generated_recommendation` (shown as "Suggested by the AI, not from your source"); a guide with no source support fails. Practice questions carry no answers.

## Glossary (`glossary`)
Settings: `max_terms` (up to 150), examples, related terms. Output: terms with `term`, `definition`, `explanation`, `example`, `topic`, `related_terms`, refs. Duplicate terms are merged (the first definition wins) and the list is sorted; unsupported terms are dropped.
`GET /study/materials/{id}/glossary?q=&topic=&order=asc|desc` searches and filters server side (owner scoped). The viewer uses it for the search box.

## Formula sheet (`formula_sheet`)
Settings: `max_formulas` (up to 60), examples, units, conditions. Each formula has name, `expression` (LaTeX, at most 600 characters), explanation, variables (symbol, meaning, unit), conditions, example, topic, refs, `needs_review`, `review_notes`.
Safety (D-98): unsafe LaTeX (links, macros, file or IO commands, HTML) is dropped and never stored; a sheet with only unsafe formulas fails. Syntax problems and undefined variables are KEPT and flagged `needs_review`; the flags are recomputed by the backend, also on edit, so a model cannot pre-approve a formula. The sheet is always `verification: "unverified"`. The viewer shows a standing "Not verified" note.
Rendering is client side with KaTeX (`frontend/src/features/study/latex.tsx`): `trust: false`, `strict: "ignore"`, macro expansion and size limits, rendered into the DOM by KaTeX (no raw HTML from the model). A failed parse is shown as plain text.

## Question bank (`question_bank`)
Settings: `count` (up to 100), `question_types`, `difficulty`. Same validation as quizzes; each question has a `topic`. The material content is the public view (question, options, type, difficulty, topic, references; no key, explanation or rubric) with a topic then difficulty outline. `GET /study/materials/{id}/questions?q=&topic=&difficulty=&question_type=` filters. Answer keys exist only in `quiz_questions`, so a bank can be practised as a quiz.

## Prompts
Registered and versioned (all `v1`): `study_guide`, `study_glossary`, `study_formula_sheet`, `study_question_bank`, plus `study_common` rules. A test asserts they are registered.

## Tests
`backend/tests/study/test_guides_banks.py`; `frontend/src/features/study/study.test.tsx` (formula note, LaTeX safety); `frontend/e2e/study.spec.ts` (glossary search, formula rendering and flagged formula).
