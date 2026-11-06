import hashlib
from collections.abc import AsyncIterator

from app.core.config import AppEnv, get_settings
from app.storage.base import (
    PutResult,
    StorageBackend,
    StorageError,
    StorageNotFoundError,
    StorageTooLargeError,
)


class InMemoryStorageBackend(StorageBackend):
    """For tests and local development only. Refuses to run outside development/testing (D-64)."""

    name = "memory"

    def __init__(self, app_env: AppEnv | None = None) -> None:
        env = app_env or get_settings().app_env
        if env not in (AppEnv.development, AppEnv.testing):
            raise StorageError("The in-memory storage backend is not allowed in this environment.")
        self._objects: dict[str, tuple[bytes, str]] = {}

    async def put(
        self,
        key: str,
        data: AsyncIterator[bytes],
        *,
        content_type: str,
        max_bytes: int | None = None,
    ) -> PutResult:
        buf = bytearray()
        digest = hashlib.sha256()
        async for chunk in data:
            if max_bytes is not None and len(buf) + len(chunk) > max_bytes:
                raise StorageTooLargeError("The object exceeds the size limit.")
            buf.extend(chunk)
            digest.update(chunk)
        self._objects[key] = (bytes(buf), content_type)
        return PutResult(size=len(buf), sha256=digest.hexdigest())

    async def open(self, key: str, *, chunk_size: int = 64 * 1024) -> AsyncIterator[bytes]:
        if key not in self._objects:
            raise StorageNotFoundError("Object not found.")
        body = self._objects[key][0]
        for i in range(0, len(body), chunk_size):
            yield body[i : i + chunk_size]

    async def delete(self, key: str) -> None:
        self._objects.pop(key, None)

    async def exists(self, key: str) -> bool:
        return key in self._objects

    def keys(self) -> list[str]:
        """Test helper."""
        return sorted(self._objects)
