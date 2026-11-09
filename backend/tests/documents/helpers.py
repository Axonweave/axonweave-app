"""Fixtures generated in code (D-76): no real or copyrighted documents are stored in git."""

import io
import struct
import zipfile
import zlib


def make_pdf(extra: bytes = b"") -> bytes:
    return b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n" + extra


def make_png(width: int = 2, height: int = 2) -> bytes:
    """A real PNG header with chosen dimensions; the pixel data is a single tiny IDAT stub."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(b"\x00" * 8))
        + chunk(b"IEND", b"")
    )


def make_jpeg(width: int = 2, height: int = 2) -> bytes:
    sof = b"\xff\xc0" + struct.pack(">HBHHB", 11, 8, height, width, 1) + b"\x01\x11\x00"
    return b"\xff\xd8\xff\xe0" + struct.pack(">H", 2) + sof + b"\xff\xd9"


def _zip(entries: dict[str, bytes], *, compress: int = zipfile.ZIP_DEFLATED) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compress) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


def make_docx(extra: dict[str, bytes] | None = None) -> bytes:
    entries = {
        "[Content_Types].xml": b"<Types/>",
        "word/document.xml": b"<w:document/>",
    }
    entries.update(extra or {})
    return _zip(entries)


def make_pptx(extra: dict[str, bytes] | None = None) -> bytes:
    entries = {
        "[Content_Types].xml": b"<Types/>",
        "ppt/presentation.xml": b"<p:presentation/>",
    }
    entries.update(extra or {})
    return _zip(entries)
