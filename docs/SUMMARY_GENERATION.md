# Summary generation (Phase 4)

Requirements: `PHASE4_SPEC.md` section 5. Decisions: D-91 (map-reduce), D-92 (edit, versions, regenerate), D-82 (no source text stored).
Code: `backend/app/study/generators/summary.py`, prompts `study_summary` and `study_summary_notes` (`app/ai/prompts/study.py`).

## Types and settings
`POST /api/v1/study/generations` with `generation_type: "summary"`.

| Setting | Values | Default |
|---|---|---|
| `summary_type` | `quick`, `detailed`, `section_wise`, `exam_oriented`, `beginner_friendly`, `key_point` | `detailed` |
| `detail_level` | `brief`, `standard`, `detailed` | `standard` |
| `include_examples`, `include_formulas` | bool | false |
| `include_definitions`, `include_important_terms`, `preserve_headings`, `include_source_references` | bool | true |
| `language` | free text, up to 40 characters | model default |

Unknown settings are rejected (422 `GENERATION_SETTINGS_INVALID`). Saved preferences (`PUT /study/preferences`) fill settings the request leaves out (summary length maps to `detail_level`).

## Output schema (validated, one correction call allowed)
```
{ title: string(1..200),
  sections: [ { heading: string(1..200),
                kind: overview|concept|definition|process|comparison|example|formula|takeaway|other,
                body: string(<=6000), bullets: [string(<=600)] (<=30),
                additional_explanation: bool,       // text added beyond the source, shown as a chip
                source_refs: [int] (<=30) } ]  (1..40 sections) }
```
Quick summaries are capped at 3 to 6 sections and key-point summaries at 4 to 12, by detail level. Control characters are removed from every string.

## How a summary is built
1. The source is read in reading order. If it fits the input budget it is one call.
2. If it does not, the engine runs ordered map-reduce (D-91): every chunk reaches a map step, each batch becomes notes, and ONE reducer call sees the notes of every batch. At most 30 batches and 3 condense rounds; otherwise `GENERATION_SOURCE_TOO_LARGE`. Sampling is never used for summaries.
3. `source_refs` are numbers that map to the units sent in the prompt. A reference that does not map is stripped (never trusted). The material stores a source list (rank, document id, chunk id, page or slide) and a `coverage` report (documents, chunks included, batches, complete). The UI shows a warning when `coverage.complete` is false.
4. Section headings the source does not support must be marked `additional_explanation`; the viewer labels them "Added explanation (not directly in your source)".
5. Exam-oriented summaries must not claim a topic will appear in an exam (prompt rule, tested).

## Editing and regeneration
Edit text in the viewer (`PATCH /study/materials/{id}` with `expected_version`); each save is a new version and version 1 is never changed. Regeneration (whole, or one section) is a preview job: the viewer shows Current and New side by side and applies only on request; a preview made before a later edit is refused (`PREVIEW_STALE`). Summaries from pasted text cannot be regenerated (the text is not stored).

## Tests
`backend/tests/study/test_summary.py` (type coverage, references, coverage report, map-reduce, injection, versions, regeneration, isolation); `frontend/src/features/study/study.test.tsx`; `frontend/e2e/study.spec.ts` (edit, version, restore).
