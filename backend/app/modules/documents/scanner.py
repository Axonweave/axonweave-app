"""Optional malware scanning behind an interface (D-71).

Off by default. When a real scanner is selected it is fail-closed: if it cannot be reached or
gives an answer we cannot read, the upload is refused with 503, never silently accepted. The
`clamav` backend speaks the clamd INSTREAM protocol over TCP (no extra dependency).
"""

import asyncio
import struct
from typing import BinaryIO, Protocol

from starlette.concurrency import run_in_threadpool

from app.core.config import Settings


class ScannerUnavailableError(Exception):
    code = "SCANNER_UNAVAILABLE"


class MalwareDetectedError(Exception):
    code = "MALWARE_DETECTED"


class Scanner(Protocol):
    async def scan(self, f: BinaryIO) -> None:
        """Return normally when clean. Raise ScannerUnavailableError when it cannot decide."""


class NoopScanner:
    async def scan(self, f: BinaryIO) -> None:
        return None


class UnavailableScanner:
    """Stands in for a configured-but-unimplemented scanner so uploads fail closed."""

    async def scan(self, f: BinaryIO) -> None:
        raise ScannerUnavailableError


_CHUNK = 64 * 1024


class ClamdScanner:
    """clamd INSTREAM: length-prefixed chunks, zero-length terminator, one-line reply."""

    def __init__(self, host: str, port: int, timeout: float) -> None:
        self._host, self._port, self._timeout = host, port, timeout

    async def scan(self, f: BinaryIO) -> None:
        try:
            async with asyncio.timeout(self._timeout):
                reader, writer = await asyncio.open_connection(self._host, self._port)
                try:
                    writer.write(b"zINSTREAM\0")
                    while block := await run_in_threadpool(f.read, _CHUNK):
                        writer.write(struct.pack("!I", len(block)) + block)
                        await writer.drain()
                    writer.write(struct.pack("!I", 0))
                    await writer.drain()
                    raw = await reader.read(4096)
                    reply = raw.rstrip(b"\x00\n ").decode("ascii", "replace")
                finally:
                    writer.close()
        except (OSError, TimeoutError):
            raise ScannerUnavailableError from None
        if reply.endswith("FOUND"):
            raise MalwareDetectedError
        if not reply.endswith("OK"):  # includes "ERROR": we could not decide
            raise ScannerUnavailableError


def get_scanner(settings: Settings) -> Scanner:
    backend = settings.scanner_backend.lower()
    if backend == "none":
        return NoopScanner()
    if backend == "clamav" and settings.clamav_host:
        return ClamdScanner(
            settings.clamav_host, settings.clamav_port, settings.clamav_timeout_seconds
        )
    return UnavailableScanner()
