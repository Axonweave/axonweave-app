"""Generator registry (spec 3.2 D). Adding a generator = one module + one line in `_GENERATORS`."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.core.config import AppEnv, Settings
from app.study.errors import InvalidSettingsError, UnknownGeneratorError
from app.study.generators.base import Generator, GeneratorSettings
from app.study.generators.echo import EchoGenerator
from app.study.generators.summary import SummaryGenerator

_GENERATORS: tuple[Generator, ...] = (EchoGenerator(), SummaryGenerator())


def available_generators(settings: Settings) -> list[Generator]:
    """Test-only generators are invisible in production (D-90)."""
    production = settings.app_env == AppEnv.production
    return [g for g in _GENERATORS if not (g.test_only and production)]


def get_generator(key: str, settings: Settings) -> Generator:
    for generator in available_generators(settings):
        if generator.key == key:
            return generator
    raise UnknownGeneratorError()


def validate_settings(generator: Generator, raw: dict[str, Any]) -> GeneratorSettings:
    """Validated, defaulted settings. Unknown fields and out-of-range values are 422."""
    try:
        return generator.settings_model.model_validate(raw)
    except ValidationError:
        raise InvalidSettingsError() from None


def generator_for_resource(resource_type: str, settings: Settings) -> Generator | None:
    """The generator that owns a stored resource type (used to validate edits)."""
    for generator in available_generators(settings):
        if generator.resource_type == resource_type:
            return generator
    return None
