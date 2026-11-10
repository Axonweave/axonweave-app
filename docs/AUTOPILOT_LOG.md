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
