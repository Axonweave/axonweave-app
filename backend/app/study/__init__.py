"""Common study generation engine (Phase 4 M0, docs/STUDY_GENERATION_ARCHITECTURE.md).

Every generator (summary, flashcards, quiz, ...) plugs into this package; none re-implements source
reading, prompting, validation, jobs, quotas or usage tracking.
"""
