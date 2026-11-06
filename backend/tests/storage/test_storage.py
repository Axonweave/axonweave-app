"""Storage tests (Phase 3 M1, D-64).

The same contract runs against the in-memory backend and, when an S3-compatible endpoint is
configured (the compose emulator or the CI one), against the S3 backend. In CI the S3 run is
mandatory: a missing endpoint fails instead of skipping.
"""

import ast
import os
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio

from app.core.config import AppEnv
from app.storage.base import (
    StorageBackend,
    StorageError,
    StorageNotConfiguredError,
    StorageNotFoundError,
    StorageTooLargeError,
)
from app.storage.factory import build_storage_backend
from app.storage.keys import build_original_key, is_valid_original_key
from app.storage.memory_backend import InMemoryStorageBackend
from app.storage.s3_backend import PART_SIZE
from tests import AMBIENT_STORAGE
from tests.ai.test_provider_layer import make_settings

TEST_BUCKET = f"axonweave-test-{uuid.uuid4().hex[:8]}"


def _s3_settings() -> object:
    return make_settings(
        storage_backend="s3",
        storage_endpoint_url=AMBIENT_STORAGE["STORAGE_ENDPOINT_URL"],
        storage_region=AMBIENT_STORAGE["STORAGE_REGION"] or "us-east-1",
        storage_bucket=TEST_BUCKET,
        storage_access_key_id=AMBIENT_STORAGE["STORAGE_ACCESS_KEY_ID"],
        storage_secret_access_key=AMBIENT_STORAGE["STORAGE_SECRET_ACCESS_KEY"],
    )


async def _bytes(stream: AsyncIterator[bytes]) -> bytes:
    return b"".join([c async for c in stream])


async def _source(*chunks: bytes) -> AsyncIterator[bytes]:
    for c in chunks:
        yield c


def _key() -> str:
    return build_original_key(uuid.uuid4(), uuid.uuid4(), 1, "pdf")


@pytest_asyncio.fixture(params=["memory", "s3"])
async def backend(request: pytest.FixtureRequest) -> AsyncIterator[StorageBackend]:
    if request.param == "memory":
        yield InMemoryStorageBackend(AppEnv.testing)
        return
    if not AMBIENT_STORAGE["STORAGE_ENDPOINT_URL"]:
        if os.environ.get("CI"):
            pytest.fail("CI must provide an S3-compatible endpoint (STORAGE_ENDPOINT_URL)")
        pytest.skip("no S3-compatible endpoint configured")
    from app.storage.s3_backend import S3StorageBackend

    s3 = S3StorageBackend(_s3_settings())  # type: ignore[arg-type]
    await s3.ensure_bucket()
    yield s3
    await s3.aclose()


# ── contract: both backends ──────────────────────────────────────────────────


async def test_round_trip_streams_back_identical_bytes(backend: StorageBackend) -> None:
    key = _key()
    result = await backend.put(key, _source(b"hello ", b"world"), content_type="application/pdf")
    assert result.size == 11
    assert len(result.sha256) == 64
    assert await _bytes(backend.open(key, chunk_size=4)) == b"hello world"
    await backend.delete(key)


async def test_checksum_matches_content(backend: StorageBackend) -> None:
    import hashlib

    key = _key()
    data = os.urandom(5000)
    result = await backend.put(key, _source(data[:2000], data[2000:]), content_type="text/plain")
    assert result.sha256 == hashlib.sha256(data).hexdigest()
    await backend.delete(key)


async def test_exists_and_delete(backend: StorageBackend) -> None:
    key = _key()
    assert not await backend.exists(key)
    await backend.put(key, _source(b"x"), content_type="text/plain")
    assert await backend.exists(key)
    await backend.delete(key)
    assert not await backend.exists(key)


async def test_delete_missing_object_succeeds(backend: StorageBackend) -> None:
    await backend.delete(_key())  # idempotent: the outbox retries safely


async def test_open_missing_object_raises_not_found(backend: StorageBackend) -> None:
    with pytest.raises(StorageNotFoundError):
        await _bytes(backend.open(_key()))


async def test_empty_object(backend: StorageBackend) -> None:
    key = _key()
    result = await backend.put(key, _source(), content_type="text/plain")
    assert result.size == 0
    assert await _bytes(backend.open(key)) == b""
    await backend.delete(key)


async def test_size_limit_aborts_and_stores_nothing(backend: StorageBackend) -> None:
    key = _key()
    with pytest.raises(StorageTooLargeError):
        await backend.put(
            key, _source(b"a" * 600, b"b" * 600), content_type="text/plain", max_bytes=1000
        )
    assert not await backend.exists(key)


async def test_overwrite_replaces_content(backend: StorageBackend) -> None:
    key = _key()
    await backend.put(key, _source(b"one"), content_type="text/plain")
    await backend.put(key, _source(b"two"), content_type="text/plain")
    assert await _bytes(backend.open(key)) == b"two"
    await backend.delete(key)


async def test_failing_source_leaves_no_object(backend: StorageBackend) -> None:
    async def broken() -> AsyncIterator[bytes]:
        yield b"partial"
        raise RuntimeError("client went away")

    key = _key()
    with pytest.raises(RuntimeError):
        await backend.put(key, broken(), content_type="text/plain")
    assert not await backend.exists(key)


async def test_errors_do_not_leak_keys_or_endpoints(backend: StorageBackend) -> None:
    key = _key()
    try:
        await _bytes(backend.open(key))
    except StorageError as exc:
        assert key not in str(exc)
        assert "http" not in str(exc).lower()


# ── S3 only ──────────────────────────────────────────────────────────────────


async def test_s3_multipart_upload_streams_a_large_object() -> None:
    if not AMBIENT_STORAGE["STORAGE_ENDPOINT_URL"]:
        if os.environ.get("CI"):
            pytest.fail("CI must provide an S3-compatible endpoint")
        pytest.skip("no S3-compatible endpoint configured")
    import hashlib

    from app.storage.s3_backend import S3StorageBackend

    s3 = S3StorageBackend(_s3_settings())  # type: ignore[arg-type]
    await s3.ensure_bucket()
    key = _key()
    block = os.urandom(1024 * 1024)
    parts = 2 * PART_SIZE // len(block) + 3  # a little over two parts, so 3 parts are sent
    digest = hashlib.sha256()

    async def big() -> AsyncIterator[bytes]:
        for _ in range(parts):
            digest.update(block)
            yield block

    try:
        result = await s3.put(key, big(), content_type="application/octet-stream")
        assert result.size == parts * len(block)
        assert result.sha256 == digest.hexdigest()
        read = hashlib.sha256()
        async for chunk in s3.open(key, chunk_size=256 * 1024):
            read.update(chunk)
        assert read.hexdigest() == digest.hexdigest()
    finally:
        await s3.delete(key)
        await s3.aclose()


# ── memory backend guard, factory, keys ──────────────────────────────────────


def test_memory_backend_refuses_production() -> None:
    with pytest.raises(StorageError):
        InMemoryStorageBackend(AppEnv.production)


def test_factory_refuses_unconfigured_storage() -> None:
    with pytest.raises(StorageNotConfiguredError):
        build_storage_backend(make_settings(storage_backend=""))


def test_valid_key_shape() -> None:
    uid, did = uuid.uuid4(), uuid.uuid4()
    key = build_original_key(uid, did, 3, "PDF")
    assert key == f"users/{uid}/documents/{did}/v3/original.pdf"
    assert is_valid_original_key(key)


@pytest.mark.parametrize("ext", ["exe", "pdf/../x", "", "html", "pdf ", "../../etc/passwd", "p.df"])
def test_key_builder_rejects_unknown_extensions(ext: str) -> None:
    with pytest.raises(ValueError):
        build_original_key(uuid.uuid4(), uuid.uuid4(), 1, ext)


def test_key_builder_takes_uuids_not_strings() -> None:
    with pytest.raises(TypeError):
        build_original_key("../../etc", uuid.uuid4(), 1, "pdf")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        build_original_key(uuid.uuid4(), "x/../y", 1, "pdf")  # type: ignore[arg-type]


@pytest.mark.parametrize("version", [0, -1, True])
def test_key_builder_rejects_bad_versions(version: int) -> None:
    with pytest.raises(ValueError):
        build_original_key(uuid.uuid4(), uuid.uuid4(), version, "pdf")


@pytest.mark.parametrize(
    "key",
    [
        "../../etc/passwd",
        "users/x/documents/y/v1/original.pdf",
        f"users/{uuid.uuid4()}/documents/{uuid.uuid4()}/v1/original.pdf/../../x",
        f"/users/{uuid.uuid4()}/documents/{uuid.uuid4()}/v1/original.pdf",
        f"users/{uuid.uuid4()}/documents/{uuid.uuid4()}/v1/evil.pdf",
        f"users/{uuid.uuid4()}/documents/{uuid.uuid4()}/v0/original.pdf",
        "",
    ],
)
def test_is_valid_original_key_rejects_foreign_keys(key: str) -> None:
    assert not is_valid_original_key(key)


def test_no_s3_sdk_imported_outside_s3_backend() -> None:
    """Only app/storage/s3_backend.py may import boto3 or botocore (CLAUDE.md rule 13)."""
    allowed = Path("app/storage/s3_backend.py").resolve()
    offenders: list[str] = []
    for path in Path("app").rglob("*.py"):
        if path.resolve() == allowed:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            if any(
                n.split(".")[0] in {"boto3", "botocore", "aioboto3", "aiobotocore"} for n in names
            ):
                offenders.append(str(path))
    assert offenders == []
