# Autopilot decisions log
Format: `TASK_ID | question | choice | reason`

P4-0 | Generic `POST /study/generations` instead of per-type endpoints (spec 19.1) | Generic route plus `GET /study/generators` for M0 | Only the echo generator exists; per-type routes arrive with each generator and can wrap the same service.
P4-0 | Where does a user read what a job produced? | Minimal `GET /study/materials/{id}` in M0 | A completed job is useless without a way to read its result; M5 extends it into the full library API.
P4-0 | Does the worker need LLM env vars? | Added a compose `x-llm-env` anchor to the worker | Generation runs in the worker (D-84); without it every job would fail `LLM_NOT_CONFIGURED`. The Gemini host is already allow-listed (D-77).
P4-0 | `ai_usage_records.request_kind` migration | None needed | `generation` was already allowed by migration 0003.
P4-0 | Source chunk-collection selection (spec 3.2 A) | Deferred | Needs a chunk-id ownership API; document, chapter, subject, folder, workspace and pasted text cover the user journeys. Recorded in D-79.
P4-0 | Is a stale running job restarted? | Failed, never restarted | Spec 17.3: do not restart an expensive generation of uncertain outcome (D-85).
P4-0 | Material status values | `completed`, `failed` only; the material row is created on success | Jobs carry in-flight status; a half-built material would need cleanup rules.
P4-0 | Which tasks count toward the daily generation quota | All jobs except failed/cancelled ones with zero provider calls | Nothing was spent in those cases.
P4-1 | Where does a regenerate preview live? | `generation_jobs.preview` JSONB (migration 0005) | A preview is not a material; a new table or a draft material would need cleanup rules.
P4-1 | Section regeneration source | Retrieval by section heading, sampled fallback when nothing matches | Cheaper than re-reading the whole chapter; still reports what was used.
P4-1 | Minimum source for a summary | 20 estimated tokens, refused before any provider call (422 `GENERATION_SOURCE_TOO_SMALL`) | A near-empty source can only produce invented text.
P4-1 | Do edits obey generation caps (section count)? | No, only structure, unique headings and real references | The cap is a generation quality rule, not a limit on the user.
P4-1 | M0 test asserting no generator in production | Updated to expect only `summary` | echo is still hidden; the assertion encoded "no real generators yet".
P4-2 | Flashcard storage: own tables or study_materials only? | Own tables `flashcard_sets` + `flashcards`, material keeps version-1 snapshot | Spec 18.4 allows either; per-card edit, reorder, favourite and selective regenerate need rows.
P4-2 | Generated card with no valid source number | Dropped, not failed | Unsupported content must not be kept (6.5), but one bad reference should not cost the whole job.
P4-2 | Near-duplicate threshold | Word-set Jaccard >= 0.8 after removing filler words | Cheap, deterministic, no embedding call; catches "What is X" vs "Define X".
P4-2 | How regenerate-selected protects edits | Per-card `revision` stored in the preview; apply is 409 if any changed | Satisfies "do not overwrite user edits" without locking cards.
P4-2 | Reorder endpoint shape | `PUT /study/flashcards/{set_id}/order` with the full ordered id list | Spec has none; full list is unambiguous and validated against the set.
P4-2 | Max cards | 50 per generation, 200 per set, 30 per regenerate | Cost control (6.3); constants, not env, since settings models cannot see app settings.
P4-3 | Where answer keys live | Only `quiz_questions`; material content stores title and counts | The generic material and version endpoints would otherwise return the key (D-94).
P4-3 | Retake policy | Unlimited retakes (cap 100), one open attempt, resume on start | Spec says define it; simplest safe option (D-95).
P4-3 | Timer | Server deadline, lazy auto-submit on next access, 10 s submit grace | No background worker needed; client cannot extend time (D-95).
P4-3 | Subjective questions | Not auto-graded; self-assessment with model answer and rubric after submit | LLM grading costs money and is optional in the spec (D-96).
P4-3 | Show explanations immediately | Not offered; only after_submission | Immediate feedback would reveal keys before submission.
P4-3 | Question editing | Not implemented in M3 | Not listed under M3; library editing is M5.
P4-3 | Multiple select scoring | Exact match, one point | Spec 7.7.
