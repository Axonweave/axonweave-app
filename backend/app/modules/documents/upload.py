"""Reads a multipart upload from the request with a hard cap on the bytes accepted (D-71).

The cap is enforced on the raw body as it arrives, before and while the form is parsed, so an
oversize or endless upload is cut off instead of being buffered. Starlette keeps file parts in
spooled temporary files (memory up to 1 MiB, then disk), never whole in memory.
"""

import uuid
from dataclasses import dataclass, field

from fastapi import HTTPException, Request
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException

from app.core.config import Settings

_OVERHEAD = 1024 * 1024  # multipart boundaries, headers and the small text fields


class BodyTooLargeError(Exception):
    pass


@dataclass
class UploadForm:
    workspace_id: uuid.UUID
    subject_id: uuid.UUID | None
    folder_id: uuid.UUID | None
    chapter_id: uuid.UUID | None
    files: list[UploadFile] = field(default_factory=list)


def _http(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def _too_large() -> HTTPException:
    return _http(413, "UPLOAD_TOO_LARGE", "The upload is too large.")


def _uuid_field(form: object, name: str, *, required: bool) -> uuid.UUID | None:
    raw = form.get(name)  # type: ignore[attr-defined]
    if raw is None or raw == "":
        if required:
            raise _http(422, "INVALID_UPLOAD", f"{name} is required.")
        return None
    if isinstance(raw, UploadFile):
        raise _http(422, "INVALID_UPLOAD", f"{name} is invalid.")
    try:
        return uuid.UUID(str(raw))
    except ValueError:
        raise _http(422, "INVALID_UPLOAD", f"{name} is invalid.") from None


async def read_upload_form(
    request: Request, settings: Settings, *, single_file: bool = False
) -> UploadForm:
    """`single_file` is the replace-file form: exactly one file, no placement fields."""
    max_files = 1 if single_file else settings.doc_max_files_per_request
    limit = max_files * settings.doc_max_file_bytes + _OVERHEAD
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > limit:
        raise _too_large()
    content_type = request.headers.get("content-type", "")
    if not content_type.lower().startswith("multipart/form-data"):
        raise _http(415, "UNSUPPORTED_MEDIA_TYPE", "Send the upload as multipart/form-data.")

    received = 0
    original_receive = request._receive  # noqa: SLF001 - the ASGI receive channel, wrapped to count

    async def counting_receive():  # type: ignore[no-untyped-def]
        nonlocal received
        message = await original_receive()
        if message["type"] == "http.request":
            received += len(message.get("body", b""))
            if received > limit:
                raise BodyTooLargeError
        return message

    limited = Request(request.scope, counting_receive)
    try:
        form = await limited.form(max_files=max_files + 1, max_fields=10)
    except BodyTooLargeError:
        raise _too_large() from None
    except MultiPartException:
        raise _http(422, "INVALID_UPLOAD", "The upload could not be read.") from None

    files = [v for v in form.getlist("files") if isinstance(v, UploadFile)]
    if not files:
        raise _http(422, "NO_FILES", "Attach at least one file in the 'files' field.")
    if len(files) > max_files:
        raise _http(422, "TOO_MANY_FILES", "Too many files in one request.")
    if single_file:
        return UploadForm(
            workspace_id=uuid.UUID(int=0),
            subject_id=None,
            folder_id=None,
            chapter_id=None,
            files=files,
        )
    return UploadForm(
        workspace_id=_uuid_field(form, "workspace_id", required=True),  # type: ignore[arg-type]
        subject_id=_uuid_field(form, "subject_id", required=False),
        folder_id=_uuid_field(form, "folder_id", required=False),
        chapter_id=_uuid_field(form, "chapter_id", required=False),
        files=files,
    )
