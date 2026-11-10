"""The single structured-output validation path (D-81).

`validate_output` parses the model text as JSON, validates it with the generator's Pydantic model,
and applies the generator's semantic checks. Anything wrong raises `OutputInvalid` carrying only
field paths and rule names, which the engine sends back in exactly one correction request. Neither
this module nor its errors ever include the model output or the source text.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from typing import Any

from pydantic import ValidationError

from app.study.generators.base import Generator, GeneratorSettings, OutputInvalid

MAX_RAW_CHARS = 300_000
_FENCE = re.compile(r"^\s*```(?:json)?\s*\n?(.*?)\n?```\s*$", re.DOTALL | re.IGNORECASE)
_SPACES = re.compile(r"\s+")


def clean_refs(refs: Sequence[int], source_count: int) -> list[int]:
    """Keep source numbers that map to a real source, once each, in first-seen order. Invalid ones
    are stripped, as Phase 3 does with citations: model-generated references are never trusted."""
    seen: list[int] = []
    for ref in refs:
        if 1 <= ref <= source_count and ref not in seen:
            seen.append(ref)
    return seen


def find_duplicates(texts: Sequence[str]) -> list[int]:
    """Indexes of items whose text repeats an earlier one (case and whitespace insensitive)."""
    seen: set[str] = set()
    dupes: list[int] = []
    for i, text in enumerate(texts):
        key = _SPACES.sub(" ", text).strip().casefold()
        if key in seen:
            dupes.append(i)
        seen.add(key)
    return dupes


def parse_json_object(raw: str) -> dict[str, Any]:
    if len(raw) > MAX_RAW_CHARS:
        raise OutputInvalid("output: too large")
    text = raw.strip()
    fenced = _FENCE.match(text)
    if fenced:
        text = fenced.group(1).strip()
    try:
        data = json.loads(text)
    except ValueError:
        raise OutputInvalid("output: not valid JSON") from None
    if not isinstance(data, dict):
        raise OutputInvalid("output: expected a JSON object")
    return data


def describe_errors(exc: ValidationError) -> str:
    """Field paths and error types only (never the offending values), capped in length."""
    parts: list[str] = []
    for err in exc.errors(include_url=False, include_context=False, include_input=False)[:12]:
        loc = ".".join(str(p) for p in err["loc"]) or "output"
        parts.append(f"{loc}: {err['type']}")
    return "; ".join(parts)[:600]


def validate_output(
    generator: Generator, raw: str, settings: GeneratorSettings, source_count: int
) -> Any:
    data = parse_json_object(raw)
    try:
        output = generator.output_model.model_validate(data)
    except ValidationError as exc:
        raise OutputInvalid(describe_errors(exc)) from None
    return generator.finalize(output, source_count, settings)
