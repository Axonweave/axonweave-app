# Phase 4 environment variables (placeholders only)

Add these to `.env.example` when convenient (the autopilot run could not edit that file). All are optional; the defaults shown are used when a variable is absent. None is a secret. Generation also needs the Phase 2 LLM settings (`LLM_PROVIDER`, `LLM_DEFAULT_MODEL`, `GEMINI_API_KEY`) and the Phase 3 Redis/Celery settings; without them the generation endpoints answer 503.

```
# Study generation (Phase 4, D-81, D-85, D-88)
STUDY_GENERATION_MODEL=                      # internal model id; empty = the default model
STUDY_MAX_INPUT_TOKENS=60000                 # per request, also capped at 80% of the model's verified limit
STUDY_MAX_OUTPUT_TOKENS=4000
STUDY_MAX_SCOPE_TOKENS=500000                # refuse scopes larger than this for batch reads
STUDY_MAX_SOURCES_PER_REQUEST=50             # documents in one request
STUDY_MAX_TEXT_SOURCE_CHARS=20000            # pasted text source
STUDY_DAILY_GENERATION_QUOTA=20              # jobs per user per UTC day
STUDY_MAX_ACTIVE_JOBS_PER_USER=2
STUDY_REQUESTS_PER_MINUTE_PER_USER=10
STUDY_PROVIDER_MAX_RETRIES=1                 # transient provider errors only; never after a timeout
STUDY_JOB_TIMEOUT_SECONDS=540                # must be below the soft limit
STUDY_TASK_SOFT_TIME_LIMIT_SECONDS=570
STUDY_TASK_HARD_TIME_LIMIT_SECONDS=600
STUDY_STALE_JOB_SECONDS=900                  # running job with no heartbeat for this long is failed
STUDY_CANCEL_POLL_SECONDS=1.0
```

The compose API and worker containers receive the LLM variables and every `STUDY_*` variable above through the `x-llm-env` anchor in `docker-compose.yml`. The running containers need `docker compose up -d` to pick up the change.
