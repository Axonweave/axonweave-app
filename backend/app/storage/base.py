from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass


class StorageError(Exception):
    """Storage failure. `code` is safe to log and return; messages never contain keys or paths."""

    code = "STORAGE_ERROR"

    def __init__(self, message: str = "Storage operation failed.") -> None:
        super().__init__(message)


class StorageNotConfiguredError(StorageError):
    code = "STORAGE_NOT_CONFIGURED"


class StorageNotFoundError(StorageError):
    code = "STORAGE_OBJECT_NOT_FOUND"


class StorageTooLargeError(StorageError):
    code = "STORAGE_OBJECT_TOO_LARGE"


@dataclass(frozen=True)
class PutResult:
    size: int
    sha256: str  # hex digest of the stored bytes


class StorageBackend(ABC):
    """Private object storage. Implementations never expose public URLs (D-64)."""

    name: str

    @abstractmethod
    async def put(
        self,
        key: str,
        data: AsyncIterator[bytes],
        *,
        content_type: str,
        max_bytes: int | None = None,
    ) -> PutResult:
        """Store a stream under `key`. With `max_bytes`, abort and store nothing when exceeded
        (StorageTooLargeError), so an oversize upload is never buffered whole or kept."""

    @abstractmethod
    def open(self, key: str, *, chunk_size: int = 64 * 1024) -> AsyncIterator[bytes]:
        """Stream an object. Raises StorageNotFoundError when it does not exist."""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete an object. Deleting a missing object succeeds (idempotent; outbox retries)."""

    @abstractmethod
    async def exists(self, key: str) -> bool: ...

    async def aclose(self) -> None:
        return None
