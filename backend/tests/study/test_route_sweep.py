"""Security sweep over EVERY study route (spec 22.7, M8): none answers without a login, and none
is reachable by guessing an id. The routes are read from the app itself, so a route added later is
covered automatically and a forgotten auth dependency fails here."""

import re
import uuid

import pytest
from httpx import AsyncClient

from app.main import app
from tests.study.conftest import Harness

STUDY_PREFIX = "/api/v1/study"


def study_routes() -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for route in app.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", None) or set()
        if path.startswith(STUDY_PREFIX):
            found.extend((m, path) for m in sorted(methods) if m not in ("HEAD", "OPTIONS"))
    return found


def fill(path: str) -> str:
    return re.sub(
        r"\{(\w+)\}", lambda m: "1" if m.group(1) == "number" else str(uuid.uuid4()), path
    )


def test_the_sweep_sees_the_whole_study_api() -> None:
    routes = study_routes()
    # 36 operations at the time of writing; a lower number means the sweep stopped seeing routes
    assert len(routes) >= 36
    paths = {p for _, p in routes}
    for expected in (
        f"{STUDY_PREFIX}/generations",
        f"{STUDY_PREFIX}/materials/{{material_id}}",
        f"{STUDY_PREFIX}/quizzes/{{quiz_id}}/results/{{attempt_id}}",
        f"{STUDY_PREFIX}/exports/{{export_id}}/download",
        f"{STUDY_PREFIX}/preferences",
    ):
        assert expected in paths


@pytest.mark.parametrize(("method", "path"), study_routes())
async def test_every_study_route_requires_a_login(
    client: AsyncClient, study: Harness, method: str, path: str
) -> None:
    resp = await client.request(method, fill(path))
    assert resp.status_code in (401, 403), f"{method} {path} answered {resp.status_code}"
    if resp.headers.get("content-type", "").startswith("application/json"):
        assert resp.json().get("success") is False
