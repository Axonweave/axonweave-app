# P4-4 plan - Study guide, glossary, formula sheet, question bank (backend only)

1. Prompts (v1) for the four generators in `app/ai/prompts/study.py`, registered.
2. `study_guide`: hierarchy-validated sections (levels 1-3, no skipped level), objectives (unsupported ones are marked as generated recommendations), prerequisites, takeaways, practice questions (no answers).
3. `glossary`: terms deduplicated by normalised term (merged), sorted, topic; search/filter/sort endpoint on a material.
4. `formula_sheet`: `app/study/latex.py` checker (balance, environments, forbidden commands/HTML). Dangerous entries are dropped; syntax or undefined-variable problems are kept but flagged `needs_review`; nothing is ever labelled verified.
5. `question_bank`: reuses M3 `question_rules`; keys stored in `quiz_questions` via a quiz row (no migration), the material payload holds only public question fields organised by topic and difficulty.
6. Registry entries; endpoint is the existing `POST /study/generations` (generation_type). Tests per spec 22.4-22.6, decisions, final PR text.
