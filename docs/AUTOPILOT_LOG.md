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
P4-4 | Endpoints for the four generators | Existing generic POST /study/generations, no per-type routes | Same as M1-M3; spec 19.1 paths are aliases the frontend does not need (D-97).
P4-4 | Invalid formula handling | Unsafe dropped, syntax/undefined variables flagged needs_review, never marked verified | Spec 10.4 forbids claiming correctness (D-98).
P4-4 | Where bank answer keys live | quiz_questions via an untimed quiz row, no new migration | Reuses M3 key protection and validation (D-99).
P4-4 | Duplicate glossary terms | Merged, first definition wins | Failing the job over a repeated term wastes cost.
P4-4 | Guide objective without a source | Kept, forced generated_recommendation=true | Spec 8.4 allows it if clearly marked.
P4-5 | Favourites (spec 12.3) | Not built | Not in the M5 task list and needs a column; flashcards already have favourites.
P4-5 | Quiz/bank duplicate | 422 DUPLICATE_NOT_SUPPORTED | Needs copying answer keys; deferred, documented in D-100.
P4-5 | Rename | Via existing PATCH edit (title in payload) | No separate endpoint; decks rename through the flashcard routes.
P4-5 | Export of quiz answer keys | Never, even after submission | Safest reading of spec 14 / 21.4; results page already shows keys after submit.
P4-5 | Export dispatch when no broker | 503 EXPORT_UNAVAILABLE | Same pattern as generation; app otherwise unaffected.
P4-5 | PDF font | Built-in Latin-1 Helvetica, non-Latin shown as ? | No font files may be committed; embedding a font is a later improvement.
P4-5 | Tests needing PyMuPDF/python-docx | Skip in the API image, run where installed | Parsers are worker-only (D-70); PDF/DOCX rendering was checked by hand in worker and locally.
P4-6 | Material id to deck or quiz id | Add `item_id` to `StudyMaterialOut` | The UI could not otherwise reach `/study/flashcards/{id}` or `/study/quizzes/{id}`; smallest backend change, owner scoped, tested.
P4-6 | Where the Study materials tab lives | Own page `/study`, linked from Library page tabs and sidebar | Library is a documents page with upload state; a separate route keeps both simple.
P4-6 | Safe LaTeX library | KaTeX 0.19.1 | 0.16.22 had advisory GHSA-238p-pmpm-9mq7 (trust bypass); upgraded before shipping.
P4-6 | Quota hint in the dialog | Shows the user's 30-day request count from the usage summary | No remaining-allowance endpoint exists; limit errors are shown by name when hit.
P4-6 | Edit UI for generated payloads | Generic text editor over the payload (locked: refs, kinds, flags) | Backend revalidates on save; avoids one bespoke form per type.
P4-6 | E2E without a model | `seed_study_e2e.py` creates materials directly; generate flow tested to its failure state only on `LLM_PROVIDER=fake` | Fake provider cannot write study JSON; never call a paid provider in tests.
P4-7 | Auto-submit at zero | Client submits, server stays authoritative | Server finalises expired attempts itself; client submit only speeds the redirect.
P4-7 | Autosave state | Latest answers kept in refs, saved debounced 700 ms | A Vitest case showed render-captured state saved empty answers.
P4-7 | Attempt list response shape | Read `data.items` | The attempts endpoint returns an object, not an array.
P4-8 | Live evaluation script | Read-only measure script plus human protocol; no separate live caller | The app already enforces job, token and quota caps; a second path could exceed them.
P4-8 | Route security sweep | Enumerate routes from the app and require login on each | New routes are covered automatically.
P4-8 | Acceptance statuses | Generation criteria are at best Partly | No live provider call, real document or visual check was run.
P3-2 | docs/API for P3-2 already merged; what to do | built only missing replace-file flow | audit showed all else present
P5-0 | Topic source | Add nullable topic to quiz_questions and flashcards, prompts v2 (D-102) | The bank's topic lived only in JSON; analytics needs a column.
P5-0 | FSRS library | py-fsrs 6.3.2 (MIT) pinned (D-105) | Maintained, MIT, latest on PyPI, only typing-extensions dependency; verified on PyPI 2026-11-12.
P5-0 | Stability/difficulty column type | double precision instead of DECIMAL (D-106) | Library uses floats; rounding would change schedules.
P5-0 | Fuzzing | Off by default | Uses global random; determinism needed for tests and reproducible history.
P5-0 | Spec 4.6 topic_performance | Not created; derived queries (D-108) | Task says derived first; stored aggregate only with a measured need.
P5-0 | Downgrade of abandoned attempts | Delete abandoned attempts on downgrade | The old status check cannot hold them and they carry no result.
P5-0 | Revision session cardinality | One active session per user (D-114) | Simple resume semantics; a partial unique index enforces it.
P5-0 | Recommendation target_id | No FK; ownership re-checked on read | Targets are quizzes, cards, subjects or chapters.
P5-0 | Descriptive grading usage kind | New request_kind evaluation in the M1 migration | Not needed until M1.
P5-0 | Spec route names | Reuse /study/quizzes routes; new /revision, /analytics, /recommendations (D-113) | CLAUDE.md and the task forbid duplicate routes.
P5-0 | Local tests | Run pytest inside the backend container | Host Python has no env config and .env must not be read.
