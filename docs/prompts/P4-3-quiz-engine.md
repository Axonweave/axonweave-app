# P4-3 - Phase 4 M3: Quiz generation and attempt engine
Follow docs/AUTOPILOT.md. Read CLAUDE.md, docs/DECISIONS.md, docs/PHASE4_SPEC.md (quiz/question sections) and the P4-0 engine. Backend only.
1. Question generation for the spec's types with validation per type (exactly one correct option for single choice, etc.). Answer keys and explanations live in the separate answer-keys table and are NEVER returned by any endpoint before an attempt is submitted (or beyond what the spec allows after).
2. Quiz sets: CRUD, regenerate as proposal, snapshots. Questions are stored once and referenced; no duplicate storage.
3. Attempts: start, server-side timer with authoritative expiry, server-side shuffling with a stored seed, save answers, submit (auto-submit on expiry), idempotent submit, grading on the server only, scores and per-question review after submit.
4. Tests: answer key never leaks (response-schema tests for every endpoint), timer expiry, late answers rejected, double submit, shuffle stability on resume, cross-user 404s, grading correctness for every question type.
