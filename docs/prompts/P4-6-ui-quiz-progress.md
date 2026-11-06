# P4-6 - Phase 4 M6: Frontend for quizzes, exports and progress
Follow docs/AUTOPILOT.md. Read CLAUDE.md, docs/DECISIONS.md and docs/PHASE4_SPEC.md (UI sections). Frontend work.
1. Quiz generation dialog and quiz list; quiz-taking screen with a countdown driven by the server's deadline, navigation, flagging, autosave, auto-submit on expiry, resume after refresh.
2. Results and review screens (explanations only after submit), attempt history, progress/analytics views with accessible charts.
3. Export buttons with format choice and download handling.
4. Vitest + Playwright (Fake providers): take a quiz end to end, timer expiry, refresh-resume, no answer key visible in the network responses before submit (assert in the test), cross-user isolation, mobile. List visual checks under HUMAN-NEEDED.
