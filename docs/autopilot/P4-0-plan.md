# P4-0 plan (autopilot, no approval gate)
Package `backend/app/study/` = the common generation engine; `backend/app/modules/study/` = routes/service/schemas.
- Models: study_materials, study_material_versions, generation_jobs, study_generation_preferences (+ migration 0004).
- Engine: GenerationRequest -> registry (settings schema, output schema, prompt) -> SourceReader (ordered / sampled / retrieved)
  -> context estimate -> model selection -> one structured-output path (one correction attempt) -> validate refs -> save.
- Jobs: Celery `study.run_generation`; atomic claim pending->retrieving (a redelivered job never restarts); heartbeat + sweeper fails
  stale jobs (never auto-restarts); cancel flag; fingerprint partial unique index = duplicate prevention.
- Limits/quotas: daily generation quota, active-job cap, per-minute limiter, max items/output tokens/input tokens, timeouts.
- Usage: ai_usage_records rows with request_kind=generation (one per provider call).
- Proof: fake `echo` generator (non-production only) end to end. Real generators arrive in M1+.
