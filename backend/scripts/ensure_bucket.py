"""Create the private storage bucket if it is missing (idempotent).

Run by the `storage-init` compose service. Prints no credentials.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings  # noqa: E402
from app.storage.base import StorageError  # noqa: E402
from app.storage.s3_backend import S3StorageBackend  # noqa: E402


async def main() -> int:
    settings = get_settings()
    if settings.storage_backend.lower() != "s3":
        print("STORAGE_BACKEND is not 's3'; nothing to do.")
        return 0
    backend = S3StorageBackend(settings)
    try:
        for attempt in range(30):
            try:
                await backend.ensure_bucket()
                print("Bucket ready.")
                return 0
            except StorageError:
                if attempt == 29:
                    raise
                await asyncio.sleep(2)
    except StorageError as exc:
        print(f"Failed: {exc}")
        return 1
    finally:
        await backend.aclose()
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
