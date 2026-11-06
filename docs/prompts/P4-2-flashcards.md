# P4-2 - Phase 4 M2: Flashcards
Follow docs/AUTOPILOT.md. Read CLAUDE.md, docs/DECISIONS.md, docs/PHASE4_SPEC.md (flashcard sections) and the P4-0 engine. Backend only.
1. Flashcard generation (count, difficulty, types per spec) using SourceReader sampled/retrieved mode for large scopes and ordered mode for small ones; de-duplicate near-identical cards; each card keeps its source reference.
2. Decks: CRUD for decks and cards, manual add/edit/delete, regenerate as proposal, move cards, versioned snapshots.
3. Review/study state per the spec (spaced-repetition fields if specified), study session endpoints, per-user data only.
4. Tests: validity and de-duplication, ownership 404s, regeneration proposals, snapshot restore, study-state updates, limits and quotas.
