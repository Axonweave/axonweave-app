"""Shared fixtures for the ingestion tests."""

from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def _restore_pillow_pixel_limit() -> Iterator[None]:
    """The extractors set PIL's process-wide pixel limit per call; keep tests independent."""
    try:
        from PIL import Image
    except ImportError:
        yield
        return
    saved = Image.MAX_IMAGE_PIXELS
    yield
    Image.MAX_IMAGE_PIXELS = saved
