"""S3-compatible backend. The ONLY module that imports the S3 SDK (boto3).

boto3 is synchronous, so every call runs in a worker thread. Uploads are streamed: bodies under one
part are sent with PutObject, larger ones with a multipart upload, so a whole file is never held in
memory (D-71). Errors are mapped to storage error codes; endpoint, keys and SDK messages are never
included in exceptions or logs.
"""

import asyncio
import hashlib
from collections.abc import AsyncIterator
from typing import Any

import boto3
import structlog
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import Settings
from app.storage.base import (
    PutResult,
    StorageBackend,
    StorageError,
    StorageNotConfiguredError,
    StorageNotFoundError,
    StorageTooLargeError,
)

logger = structlog.get_logger(__name__)

PART_SIZE = 8 * 1024 * 1024  # S3 minimum part size is 5 MiB (except the last)


def _is_missing(exc: ClientError) -> bool:
    code = str(exc.response.get("Error", {}).get("Code", ""))
    return code in {"404", "NoSuchKey", "NotFound", "NoSuchBucket"}


class S3StorageBackend(StorageBackend):
    name = "s3"

    def __init__(self, settings: Settings) -> None:
        if not (
            settings.storage_bucket
            and settings.storage_access_key_id
            and settings.storage_secret_access_key
        ):
            raise StorageNotConfiguredError("Object storage is not configured.")
        self._bucket = settings.storage_bucket
        self._sse = settings.storage_server_side_encryption
        self._client: Any = boto3.client(
            "s3",
            endpoint_url=settings.storage_endpoint_url or None,
            region_name=settings.storage_region,
            aws_access_key_id=settings.storage_access_key_id.get_secret_value(),
            aws_secret_access_key=settings.storage_secret_access_key.get_secret_value(),
            config=Config(
                s3={"addressing_style": "path" if settings.storage_force_path_style else "auto"},
                retries={"max_attempts": 3, "mode": "standard"},
                connect_timeout=5,
                read_timeout=30,
                signature_version="s3v4",
            ),
        )

    def _extra(self) -> dict[str, str]:
        return {"ServerSideEncryption": self._sse} if self._sse else {}

    async def ensure_bucket(self) -> None:
        """Create the private bucket if missing. Idempotent. Used by the bootstrap script."""

        def run() -> None:
            try:
                self._client.head_bucket(Bucket=self._bucket)
            except ClientError as exc:
                if not _is_missing(exc):
                    raise
                self._client.create_bucket(Bucket=self._bucket)

        try:
            await asyncio.to_thread(run)
        except (ClientError, BotoCoreError) as exc:
            logger.error("storage_ensure_bucket_failed", error_type=type(exc).__name__)
            raise StorageError("Could not prepare the storage bucket.") from None

    async def put(
        self,
        key: str,
        data: AsyncIterator[bytes],
        *,
        content_type: str,
        max_bytes: int | None = None,
    ) -> PutResult:
        digest = hashlib.sha256()
        total = 0
        buf = bytearray()
        upload_id: str | None = None
        parts: list[dict[str, Any]] = []
        extra = self._extra()

        async def send_part(body: bytes) -> None:
            nonlocal upload_id
            if upload_id is None:
                resp = await asyncio.to_thread(
                    lambda: self._client.create_multipart_upload(
                        Bucket=self._bucket, Key=key, ContentType=content_type, **extra
                    )
                )
                upload_id = str(resp["UploadId"])
            number = len(parts) + 1
            current = upload_id
            part = await asyncio.to_thread(
                lambda: self._client.upload_part(
                    Bucket=self._bucket,
                    Key=key,
                    UploadId=current,
                    PartNumber=number,
                    Body=body,
                )
            )
            parts.append({"ETag": part["ETag"], "PartNumber": number})

        try:
            async for chunk in data:
                total += len(chunk)
                if max_bytes is not None and total > max_bytes:
                    raise StorageTooLargeError("The object exceeds the size limit.")
                digest.update(chunk)
                buf.extend(chunk)
                while len(buf) >= PART_SIZE:
                    body = bytes(buf[:PART_SIZE])
                    del buf[:PART_SIZE]
                    await send_part(body)

            if upload_id is None:
                single = bytes(buf)
                await asyncio.to_thread(
                    lambda: self._client.put_object(
                        Bucket=self._bucket,
                        Key=key,
                        Body=single,
                        ContentType=content_type,
                        **extra,
                    )
                )
            else:
                if buf:
                    await send_part(bytes(buf))
                final_id = upload_id
                await asyncio.to_thread(
                    lambda: self._client.complete_multipart_upload(
                        Bucket=self._bucket,
                        Key=key,
                        UploadId=final_id,
                        MultipartUpload={"Parts": parts},
                    )
                )
            return PutResult(size=total, sha256=digest.hexdigest())
        except BaseException as exc:
            if upload_id is not None:
                aborted = upload_id
                try:
                    await asyncio.shield(
                        asyncio.to_thread(
                            lambda: self._client.abort_multipart_upload(
                                Bucket=self._bucket, Key=key, UploadId=aborted
                            )
                        )
                    )
                except Exception:  # best effort; a bucket lifecycle rule also expires these
                    logger.warning("storage_abort_multipart_failed")
            if isinstance(exc, ClientError | BotoCoreError):
                logger.error("storage_put_failed", error_type=type(exc).__name__)
                raise StorageError("Could not store the object.") from None
            raise

    async def open(self, key: str, *, chunk_size: int = 64 * 1024) -> AsyncIterator[bytes]:
        try:
            resp = await asyncio.to_thread(
                lambda: self._client.get_object(Bucket=self._bucket, Key=key)
            )
        except ClientError as exc:
            if _is_missing(exc):
                raise StorageNotFoundError("Object not found.") from None
            logger.error("storage_get_failed", error_type=type(exc).__name__)
            raise StorageError("Could not read the object.") from None
        except BotoCoreError as exc:
            logger.error("storage_get_failed", error_type=type(exc).__name__)
            raise StorageError("Could not read the object.") from None
        body = resp["Body"]
        try:
            while True:
                chunk: bytes = await asyncio.to_thread(body.read, chunk_size)
                if not chunk:
                    break
                yield chunk
        finally:
            await asyncio.shield(asyncio.to_thread(body.close))

    async def delete(self, key: str) -> None:
        try:
            await asyncio.to_thread(
                lambda: self._client.delete_object(Bucket=self._bucket, Key=key)
            )
        except (ClientError, BotoCoreError) as exc:
            logger.error("storage_delete_failed", error_type=type(exc).__name__)
            raise StorageError("Could not delete the object.") from None

    async def exists(self, key: str) -> bool:
        try:
            await asyncio.to_thread(lambda: self._client.head_object(Bucket=self._bucket, Key=key))
            return True
        except ClientError as exc:
            if _is_missing(exc):
                return False
            raise StorageError("Could not check the object.") from None
        except BotoCoreError:
            raise StorageError("Could not check the object.") from None

    async def aclose(self) -> None:
        await asyncio.to_thread(self._client.close)
