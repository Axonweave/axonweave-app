# P4-5 - Phase 4 M5: Frontend for summaries and flashcards
Follow docs/AUTOPILOT.md. Read CLAUDE.md, docs/DECISIONS.md and docs/PHASE4_SPEC.md (UI sections). Frontend work.
1. Study materials tab in the Library and entry points from subject, chapter and document pages ("Generate summary/flashcards").
2. Generation dialogs (scope, options, quota hint), job progress with polling and cancel, failure states.
3. Summary view/editor with source references, version history, regenerate-proposal review (accept/reject with diff).
4. Flashcard deck view, flip-card study mode, keyboard navigation, edit/add/delete, review state.
5. Vitest + Playwright (Fake providers) covering generate -> view -> edit -> regenerate proposal -> study; cross-user isolation; mobile. List visual checks under HUMAN-NEEDED.
