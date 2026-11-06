# Phase 3 `.env.example` block (placeholders only)

The planning session could not edit `.env.example` (the file is denied to Claude Code by the project's permission settings, and it was
deliberately not worked around). Append the block below to `.env.example` by hand in the M1 PR, then delete this file.
Names only; values are placeholders or safe defaults. Every variable must also be passed through `docker-compose.yml` (no `env_file`).

```dotenv
# ── Phase 3: object storage (S3-compatible; local emulator in docker compose) ──
STORAGE_BACKEND=s3                      # s3 | memory (memory only for tests; refused in production)
STORAGE_ENDPOINT_URL=http://objectstore:8333
STORAGE_REGION=us-east-1
STORAGE_BUCKET=axonweave-documents
STORAGE_ACCESS_KEY_ID=change_me
STORAGE_SECRET_ACCESS_KEY=change_me     # SecretStr in Settings; never logged
STORAGE_FORCE_PATH_STYLE=true
STORAGE_SERVER_SIDE_ENCRYPTION=         # e.g. AES256 where the store supports it

# ── Phase 3: Redis and Celery ──
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2
CELERY_TASK_SOFT_TIME_LIMIT_SECONDS=240
CELERY_TASK_HARD_TIME_LIMIT_SECONDS=300
CELERY_MAX_RETRIES=3
RATE_LIMIT_BACKEND=redis                # redis | memory

# ── Phase 3: embeddings (provider independent; model id must be verified, never guessed) ──
EMBEDDING_PROVIDER=                     # gemini | fake (fake only in development/testing)
EMBEDDING_MODEL=                        # set after running scripts/list_embedding_models.py
EMBEDDING_DIMENSIONS=                   # must match the verified model and the column definition
EMBEDDING_INDEX_VERSION=1
EMBEDDING_BATCH_SIZE=32
EMBEDDING_TIMEOUT_SECONDS=30

# ── Phase 3: upload and processing limits ──
DOC_MAX_FILE_BYTES=26214400             # 25 MiB
DOC_MAX_FILES_PER_REQUEST=5
DOC_MAX_DOCUMENTS_PER_USER=200
DOC_MAX_TOTAL_BYTES_PER_USER=1073741824 # 1 GiB
DOC_MAX_PAGES=500
DOC_MAX_EXTRACTED_CHARS=2000000
DOC_ZIP_MAX_ENTRIES=2000
DOC_ZIP_MAX_UNCOMPRESSED_BYTES=209715200
DOC_ZIP_MAX_RATIO=100
DOC_IMAGE_MAX_PIXELS=50000000
DOC_OCR_ENABLED=true
DOC_OCR_DPI=200
DOC_OCR_LANGUAGES=eng
SCANNER_BACKEND=none                    # none | clamav (fail-closed when clamav)
CLAMAV_HOST=
CLAMAV_PORT=3310

# ── Phase 3: chunking and retrieval ──
CHUNK_TARGET_TOKENS=650
CHUNK_OVERLAP_TOKENS=100
RETRIEVAL_TOP_K=8
RETRIEVAL_CANDIDATES=40
RETRIEVAL_MIN_SCORE=                    # set after the evaluation (D-73); empty = not configured
RETRIEVAL_RRF_K=60
RAG_CONTEXT_TOKEN_BUDGET=4000
RAG_SHORT_QUERY_CHARS=40
```

The defaults above are starting points, not measured values; revisit them in M3/M4 and record changes in `DECISIONS.md`.
