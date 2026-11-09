"""Upload validation (D-71). Pure functions: no I/O beyond the file object passed in, no parsers.

The API image is parser-free (D-70), so this module only looks at magic bytes, zip directory
metadata and image headers. Real parsing happens in the worker. Nothing here logs file content.
"""

from __future__ import annotations

import codecs
import re
import struct
import unicodedata
import zipfile
from dataclasses import dataclass
from typing import BinaryIO

CHUNK = 64 * 1024
MAX_NAME_LENGTH = 255

# detected type -> (mime, extensions accepted for it)
_TYPES: dict[str, tuple[str, frozenset[str]]] = {
    "pdf": ("application/pdf", frozenset({"pdf"})),
    "pptx": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        frozenset({"pptx"}),
    ),
    "docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        frozenset({"docx"}),
    ),
    "txt": ("text/plain", frozenset({"txt"})),
    "md": ("text/markdown", frozenset({"md"})),
    "png": ("image/png", frozenset({"png"})),
    "jpg": ("image/jpeg", frozenset({"jpg", "jpeg"})),
}
ALLOWED_UPLOAD_EXTENSIONS = frozenset(e for _, exts in _TYPES.values() for e in exts)
# "png" is stored as file_type "png"; the model's FILE_TYPES already include it.

_NESTED_ARCHIVE_SUFFIXES = (".zip", ".jar", ".7z", ".rar", ".gz", ".tgz", ".tar", ".bz2", ".xz")
_HTML_START = re.compile(rb"^\s*(<!doctype\s+html|<html|<head|<body|<script|<svg|<\?xml)", re.I)


class UploadRejected(Exception):
    """A file that must not be stored. `code` and `message` are safe to return."""

    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class Limits:
    max_file_bytes: int
    zip_max_entries: int
    zip_max_uncompressed_bytes: int
    zip_max_ratio: int
    image_max_pixels: int


@dataclass(frozen=True)
class DetectedFile:
    file_type: str  # one of FILE_TYPES
    mime_type: str


def sanitise_display_name(raw: str | None) -> str:
    """Make a safe display name: no path parts, control characters or odd whitespace.

    The result is only ever shown; it is never used to build a storage key (D-64)."""
    name = unicodedata.normalize("NFC", raw or "")
    name = re.split(r"[\\/]", name)[-1]  # drop any directory part
    name = "".join(ch for ch in name if unicodedata.category(ch)[0] != "C")
    name = re.sub(r"[<>:\"|?*]", "_", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    if not name:
        return "document"
    if len(name) > MAX_NAME_LENGTH:
        stem, dot, ext = name.rpartition(".")
        if dot and 0 < len(ext) <= 8:
            name = stem[: MAX_NAME_LENGTH - len(ext) - 1] + "." + ext
        else:
            name = name[:MAX_NAME_LENGTH]
    return name


def extension_of(name: str) -> str:
    _, dot, ext = name.rpartition(".")
    return ext.lower() if dot else ""


def measure(f: BinaryIO) -> int:
    f.seek(0, 2)
    size = f.tell()
    f.seek(0)
    return size


def detect_and_validate(f: BinaryIO, extension: str, limits: Limits) -> DetectedFile:
    """Detect the real type from content, require it to match the extension, run type checks.

    The browser's MIME type is never consulted (D-71)."""
    if extension not in ALLOWED_UPLOAD_EXTENSIONS:
        raise UploadRejected("UNSUPPORTED_FILE_TYPE", "This file type is not supported.")
    size = measure(f)
    if size == 0:
        raise UploadRejected("EMPTY_FILE", "The file is empty.")
    if size > limits.max_file_bytes:
        raise UploadRejected("FILE_TOO_LARGE", "The file is too large.", 413)

    head = f.read(16)
    f.seek(0)
    detected: str | None = None
    if head.startswith(b"%PDF-"):
        detected = "pdf"
    elif head.startswith(b"\x89PNG\r\n\x1a\n"):
        detected = "png"
    elif head.startswith(b"\xff\xd8\xff"):
        detected = "jpg"
    elif head.startswith((b"PK\x03\x04",)):
        detected = _validate_ooxml(f, limits)
    elif extension in ("txt", "md"):
        _validate_text(f)
        detected = extension
    if detected is None:
        raise UploadRejected(
            "FILE_CONTENT_MISMATCH", "The file content does not match a supported type."
        )
    if extension not in _TYPES[detected][1]:
        raise UploadRejected(
            "FILE_CONTENT_MISMATCH", "The file content does not match its extension."
        )
    if detected == "png":
        _check_pixels(_png_size(f), limits)
    elif detected == "jpg":
        _check_pixels(_jpeg_size(f), limits)
    f.seek(0)
    return DetectedFile(file_type=detected, mime_type=_TYPES[detected][0])


def _validate_text(f: BinaryIO) -> None:
    """Plain text/markdown: UTF-8, no NUL bytes, and not HTML or XML dressed up as text."""
    decoder = codecs.getincrementaldecoder("utf-8")()
    first = True
    f.seek(0)
    while chunk := f.read(CHUNK):
        if b"\x00" in chunk:
            raise UploadRejected("FILE_CONTENT_MISMATCH", "The file is not valid text.")
        if first and _HTML_START.match(chunk[:1024]):
            raise UploadRejected("HTML_NOT_ALLOWED", "HTML and XML files are not accepted.")
        first = False
        try:
            decoder.decode(chunk)
        except UnicodeDecodeError:
            raise UploadRejected(
                "FILE_CONTENT_MISMATCH", "The file is not valid UTF-8 text."
            ) from None
    try:
        decoder.decode(b"", final=True)
    except UnicodeDecodeError:
        raise UploadRejected("FILE_CONTENT_MISMATCH", "The file is not valid UTF-8 text.") from None
    f.seek(0)


def _validate_ooxml(f: BinaryIO, limits: Limits) -> str:
    """DOCX/PPTX are zip files: check the directory before anything is ever extracted (D-71).

    Headers can lie about sizes, so the worker enforces the same limits again while reading."""
    f.seek(0)
    try:
        zf = zipfile.ZipFile(f)
        infos = zf.infolist()
    except (zipfile.BadZipFile, ValueError, OSError):
        raise UploadRejected("FILE_CORRUPT", "The file could not be read.") from None
    if len(infos) > limits.zip_max_entries:
        raise UploadRejected("ARCHIVE_TOO_LARGE", "The document contains too many parts.")
    total = 0
    names: set[str] = set()
    for info in infos:
        name = info.filename
        parts = name.split("/")
        if name.startswith("/") or "\\" in name or ".." in parts or re.match(r"^[A-Za-z]:", name):
            raise UploadRejected("ARCHIVE_UNSAFE", "The document contains an unsafe path.")
        if info.flag_bits & 0x1:
            raise UploadRejected("FILE_ENCRYPTED", "Encrypted documents are not supported.")
        lowered = name.lower()
        if lowered.endswith(_NESTED_ARCHIVE_SUFFIXES):
            raise UploadRejected("ARCHIVE_UNSAFE", "Nested archives are not allowed.")
        if "vbaproject.bin" in lowered:
            raise UploadRejected("MACROS_NOT_ALLOWED", "Documents with macros are not accepted.")
        total += info.file_size
        if total > limits.zip_max_uncompressed_bytes:
            raise UploadRejected("ARCHIVE_TOO_LARGE", "The document expands to too much data.")
        if (
            info.file_size >= 64 * 1024
            and info.compress_size > 0
            and info.file_size / info.compress_size > limits.zip_max_ratio
        ):
            raise UploadRejected("ARCHIVE_TOO_LARGE", "The document is compressed suspiciously.")
        names.add(name)
    f.seek(0)
    if "[Content_Types].xml" not in names:
        raise UploadRejected("FILE_CONTENT_MISMATCH", "The file is not a supported document.")
    if "word/document.xml" in names:
        return "docx"
    if "ppt/presentation.xml" in names:
        return "pptx"
    raise UploadRejected("FILE_CONTENT_MISMATCH", "The file is not a supported document.")


def _png_size(f: BinaryIO) -> tuple[int, int]:
    f.seek(0)
    header = f.read(24)
    if len(header) < 24 or header[12:16] != b"IHDR":
        raise UploadRejected("FILE_CORRUPT", "The image could not be read.")
    width, height = struct.unpack(">II", header[16:24])
    return width, height


def _jpeg_size(f: BinaryIO) -> tuple[int, int]:
    f.seek(2)
    while True:
        marker_start = f.read(1)
        if not marker_start:
            break
        if marker_start != b"\xff":
            continue
        marker = f.read(1)
        while marker == b"\xff":  # fill bytes
            marker = f.read(1)
        if not marker:
            break
        code = marker[0]
        if code in (0x01, 0xD8) or 0xD0 <= code <= 0xD7:
            continue
        if code == 0xD9:
            break
        length_bytes = f.read(2)
        if len(length_bytes) < 2:
            break
        (length,) = struct.unpack(">H", length_bytes)
        if 0xC0 <= code <= 0xCF and code not in (0xC4, 0xC8, 0xCC):
            body = f.read(5)
            if len(body) < 5:
                break
            height, width = struct.unpack(">xHH", body)
            return width, height
        f.seek(length - 2, 1)
    raise UploadRejected("FILE_CORRUPT", "The image could not be read.")


def _check_pixels(size: tuple[int, int], limits: Limits) -> None:
    width, height = size
    if width < 1 or height < 1:
        raise UploadRejected("FILE_CORRUPT", "The image could not be read.")
    if width * height > limits.image_max_pixels:
        raise UploadRejected("IMAGE_TOO_LARGE", "The image has too many pixels.")
