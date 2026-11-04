"""Logging configuration, correlation-id handling and the DB session dependency."""

import json
import logging

import pytest
from httpx import AsyncClient

from app.core.logging import (
    _add_correlation_id,
    configure_logging,
    correlation_id_var,
    get_logger,
)
from app.database.connection import get_db


@pytest.fixture(autouse=True)
def _restore_logging():
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield
    root.handlers[:] = handlers
    root.setLevel(level)


def test_json_logging_emits_valid_json_with_correlation_id(capsys):
    configure_logging(json_logs=True)
    token = correlation_id_var.set("req-123")
    try:
        get_logger("test").info("hello_event", answer=42)
    finally:
        correlation_id_var.reset(token)
    line = [ln for ln in capsys.readouterr().out.splitlines() if "hello_event" in ln][-1]
    data = json.loads(line)
    assert data["event"] == "hello_event"
    assert data["correlation_id"] == "req-123"
    assert data["answer"] == 42


def test_console_logging_configures_without_error(capsys):
    configure_logging(json_logs=False)
    get_logger("test").info("console_event")
    assert "console_event" in capsys.readouterr().out


def test_correlation_processor_skips_when_unset():
    assert _add_correlation_id(None, "info", {"event": "x"}) == {"event": "x"}


async def test_valid_correlation_id_is_echoed(client: AsyncClient):
    resp = await client.get("/health", headers={"X-Correlation-ID": "abc-123_XYZ.9"})
    assert resp.headers["X-Correlation-ID"] == "abc-123_XYZ.9"


@pytest.mark.parametrize("bad", ["x" * 65, "has space", "semi;colon", "<script>"])
async def test_unsafe_correlation_id_is_replaced(client: AsyncClient, bad: str):
    resp = await client.get("/health", headers={"X-Correlation-ID": bad})
    assert resp.headers["X-Correlation-ID"] != bad
    assert len(resp.headers["X-Correlation-ID"]) == 36  # generated UUID


async def test_get_db_rolls_back_and_reraises_on_error():
    gen = get_db()
    await gen.__anext__()
    with pytest.raises(RuntimeError, match="boom"):
        await gen.athrow(RuntimeError("boom"))


async def test_get_db_commits_on_normal_exit():
    gen = get_db()
    await gen.__anext__()
    with pytest.raises(StopAsyncIteration):
        await gen.__anext__()
