from functools import lru_cache

from app.core.config import Settings, get_settings
from app.storage.base import StorageBackend, StorageNotConfiguredError


def build_storage_backend(settings: Settings) -> StorageBackend:
    kind = settings.storage_backend.lower()
    if kind == "s3":
        from app.storage.s3_backend import S3StorageBackend

        return S3StorageBackend(settings)
    if kind == "memory":
        from app.storage.memory_backend import InMemoryStorageBackend

        return InMemoryStorageBackend(settings.app_env)
    raise StorageNotConfiguredError("Object storage is not configured.")


@lru_cache
def _default_backend() -> StorageBackend:
    return build_storage_backend(get_settings())


def get_storage_backend() -> StorageBackend:
    """FastAPI dependency / worker accessor. Raises StorageNotConfiguredError when unset (503)."""
    return _default_backend()
