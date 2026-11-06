# P4-1 - Phase 4 M1: Summaries
Follow docs/AUTOPILOT.md. Read CLAUDE.md, docs/DECISIONS.md, docs/PHASE4_SPEC.md (summary sections) and the P4-0 engine. Backend only.
1. Summary generation for document, chapter, subject scopes with the spec's styles/lengths. Whole-chapter summaries use ordered map-reduce so no part is silently skipped; report which sources were included.
2. Source attribution: each summary section references source documents/pages using the same validation approach as Phase 3 citations (invalid references stripped).
3. APIs: create (starts job), list, get, update (user edits), delete, regenerate as a proposal (user accepts or rejects; the old content stays until accepted), version history and restore.
4. Tests: ownership 404s, scope resolution, ordered coverage (every chunk reaches the reducer), empty/insufficient source handling, regeneration proposal flow, version restore, no content in logs, prompt injection inside a document is not followed.
