"""Optional malware scanning behind an interface (D-71).

Off by default. When a real scanner is selected it is fail-closed: if it cannot be reached the
upload is refused with 503, never silently accepted. Only the interface and the `none` backend
exist so far; selecting `clamav` therefore refuses every upload until an adapter is added.
"""

from typing import BinaryIO, Protocol

from app.core.config import Settings


class ScannerUnavailableError(Exception):
    code = "SCANNER_UNAVAILABLE"


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


def get_scanner(settings: Settings) -> Scanner:
    if settings.scanner_backend.lower() == "none":
        return NoopScanner()
    return UnavailableScanner()
