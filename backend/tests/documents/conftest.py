"""Document tests never talk to a real broker: jobs go to a recording fake dispatcher."""

import uuid
from collections.abc import Iterator

import pytest


class FakeDispatcher:
    def __init__(self) -> None:
        self.sent: list[uuid.UUID] = []
        self.is_available = True

    def available(self) -> bool:
        return self.is_available

    def dispatch(self, job_id: uuid.UUID) -> bool:
        self.sent.append(job_id)
        return True


@pytest.fixture(autouse=True)
def dispatcher(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeDispatcher]:
    fake = FakeDispatcher()
    monkeypatch.setattr("app.modules.documents.service.get_job_dispatcher", lambda: fake)
    yield fake
