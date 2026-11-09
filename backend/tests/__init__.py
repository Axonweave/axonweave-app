"""Test package. The environment below is set before conftest and any `app` import.

Phase 3 services (Redis, object storage, embeddings) are real in the dev and CI stacks, but tests
must not depend on them by accident: the rate limiter is in-process, and storage and embeddings are
unset unless a test builds its own Settings or clients (the storage contract tests do, from
`AMBIENT_STORAGE` below).
"""

import os

# Real storage settings from the environment (compose or CI), kept for the S3 contract tests only.
AMBIENT_STORAGE: dict[str, str] = {
    name: os.environ.get(name, "")
    for name in (
        "STORAGE_ENDPOINT_URL",
        "STORAGE_REGION",
        "STORAGE_ACCESS_KEY_ID",
        "STORAGE_SECRET_ACCESS_KEY",
    )
}
AMBIENT_REDIS_URL = os.environ.get("REDIS_URL", "")

os.environ["RATE_LIMIT_BACKEND"] = "memory"
os.environ["STORAGE_BACKEND"] = ""
os.environ["EMBEDDING_PROVIDER"] = ""
