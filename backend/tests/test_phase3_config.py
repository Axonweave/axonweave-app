"""Phase 3 configuration: defaults keep the app running, production fails fast (D-62..D-71)."""

import pytest
from pydantic import ValidationError

from app.database.vector import EMBEDDING_COLUMN_DIMENSIONS
from tests.ai.test_provider_layer import make_settings

PROD = {
    "app_env": "production",
    "cookie_secure": True,
    "frontend_url": "https://app.example.com",
    "app_secret_key": "x" * 40,
}
GOOD_STORAGE = {
    "storage_backend": "s3",
    "storage_endpoint_url": "https://s3.example.com",
    "storage_bucket": "docs",
    "storage_access_key_id": "AKIAREALKEY0000",
    "storage_secret_access_key": "realsecretrealsecretrealsecret",
    "celery_broker_url": "redis://redis:6379/1",
    "rate_limit_backend": "redis",
    "redis_url": "redis://redis:6379/0",
}


def prod(**over: object):  # type: ignore[no-untyped-def]
    return make_settings(**{**PROD, **GOOD_STORAGE, **over})


def test_the_app_configures_without_any_phase3_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("REDIS_URL", "CELERY_BROKER_URL", "CELERY_RESULT_BACKEND", "STORAGE_ENDPOINT_URL"):
        monkeypatch.delenv(name, raising=False)  # the dev stack sets these; this is the bare case
    s = make_settings()
    assert s.storage_backend == "" and s.embedding_provider == "" and s.redis_url == ""
    assert s.rate_limit_backend == "memory"
    assert s.embedding_dimensions == EMBEDDING_COLUMN_DIMENSIONS


def test_a_valid_production_configuration_is_accepted() -> None:
    assert prod().storage_backend == "s3"


def test_blank_credentials_from_compose_become_none() -> None:
    s = make_settings(storage_access_key_id="", storage_secret_access_key="  ")
    assert s.storage_access_key_id is None and s.storage_secret_access_key is None


def test_secrets_are_not_printed() -> None:
    s = make_settings(storage_access_key_id="AKIASECRETVALUE", storage_secret_access_key="s3cr3t")
    text = repr(s) + str(s.model_dump())
    assert "AKIASECRETVALUE" not in text and "s3cr3t" not in text


def test_memory_storage_is_refused_in_production() -> None:
    with pytest.raises(ValidationError, match="STORAGE_BACKEND=memory"):
        make_settings(app_env="production", storage_backend="memory")


@pytest.mark.parametrize("env", ["development", "testing"])
def test_memory_storage_is_allowed_for_development_and_tests(env: str) -> None:
    assert make_settings(app_env=env, storage_backend="memory").storage_backend == "memory"


def test_fake_embedder_is_refused_in_production() -> None:
    with pytest.raises(ValidationError, match="EMBEDDING_PROVIDER=fake"):
        prod(embedding_provider="fake")
    assert make_settings(embedding_provider="fake").embedding_provider == "fake"


@pytest.mark.parametrize(
    ("over", "message"),
    [
        ({"storage_endpoint_url": ""}, "STORAGE_"),
        ({"storage_bucket": ""}, "STORAGE_"),
        ({"storage_access_key_id": None}, "STORAGE_"),
        ({"storage_secret_access_key": None}, "STORAGE_"),
        ({"storage_access_key_id": "change_me"}, "placeholders"),
        ({"storage_secret_access_key": "replace_me_please"}, "placeholders"),
        ({"storage_access_key_id": "axonweave_dev_access"}, "development defaults"),
        ({"storage_endpoint_url": "http://s3.example.com"}, "https"),
        ({"celery_broker_url": ""}, "CELERY_BROKER_URL"),
    ],
)
def test_production_fails_fast_on_missing_or_placeholder_values(
    over: dict[str, object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        prod(**over)


def test_production_without_storage_is_allowed_when_documents_are_not_enabled() -> None:
    """The app must run without document features (CLAUDE.md rule 13)."""
    s = make_settings(**PROD, rate_limit_backend="redis", redis_url="redis://r:6379/0")
    assert s.storage_backend == ""


def test_redis_limiter_needs_a_redis_url() -> None:
    with pytest.raises(ValidationError, match="REDIS_URL"):
        make_settings(rate_limit_backend="redis", redis_url="")


@pytest.mark.parametrize(
    "over",
    [
        {"storage_backend": "ftp"},
        {"rate_limit_backend": "etcd"},
        {"scanner_backend": "magic"},
        {"celery_task_soft_time_limit_seconds": 300, "celery_task_hard_time_limit_seconds": 300},
    ],
)
def test_nonsense_values_are_rejected(over: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        make_settings(**over)


def test_embedding_dimension_must_match_the_column_once_an_embedder_is_set() -> None:
    make_settings(embedding_dimensions=512)  # unused embedder: no error
    with pytest.raises(ValidationError, match="does not match the vector column"):
        make_settings(embedding_provider="gemini", embedding_dimensions=512)
    ok = make_settings(
        embedding_provider="gemini", embedding_dimensions=EMBEDDING_COLUMN_DIMENSIONS
    )
    assert ok.embedding_provider == "gemini"
