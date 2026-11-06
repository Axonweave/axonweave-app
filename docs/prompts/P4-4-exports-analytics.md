# P4-4 - Phase 4 M4: Export, history and analytics
Follow docs/AUTOPILOT.md. Read CLAUDE.md, docs/DECISIONS.md and docs/PHASE4_SPEC.md (export, history, progress sections). Backend only.
1. Exports in the spec's formats (CSV, JSON, PDF/Markdown as specified). CSV cells starting with =, +, -, @, tab or CR are neutralised. Exports contain only the caller's data; quiz exports respect answer-key rules.
2. Attempt history, per-topic performance and progress endpoints, aggregated in SQL with ownership filters.
3. Account export/deletion cover all Phase 4 data.
4. Tests: formula-injection payloads, ownership, deletion cascade, aggregate correctness on seeded data.
