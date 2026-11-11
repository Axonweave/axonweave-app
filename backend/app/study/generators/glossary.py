"""Glossary generator (spec 9): term extraction, definitions, merged duplicates, source references.

Terms are sorted alphabetically and a term that repeats (case, spacing or trailing punctuation
differences) is merged into the first one instead of failing the job.
"""

from __future__ import annotations

import re
from typing import Annotated, Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from app.ai.prompts import study as prompts
from app.study.generators.base import Generator, GeneratorSettings, OutputInvalid
from app.study.schemas import CleanStr
from app.study.validation import clean_refs

MAX_TERMS = 150
_SPACES = re.compile(r"\s+")


class GlossarySettings(GeneratorSettings):
    max_terms: int = Field(default=30, ge=1, le=MAX_TERMS)
    include_examples: bool = True
    include_related_terms: bool = True


class TermOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    term: Annotated[CleanStr, Field(min_length=1, max_length=150)]
    definition: Annotated[CleanStr, Field(min_length=1, max_length=1500)]
    explanation: Annotated[CleanStr, Field(max_length=2000)] = ""
    example: Annotated[CleanStr, Field(max_length=1000)] = ""
    topic: Annotated[CleanStr, Field(max_length=120)] = ""
    related_terms: list[Annotated[CleanStr, Field(min_length=1, max_length=150)]] = Field(
        default_factory=list, max_length=15
    )
    source_refs: list[int] = Field(default_factory=list, max_length=20)


class GlossaryOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Annotated[CleanStr, Field(min_length=1, max_length=200)]
    terms: list[TermOut] = Field(min_length=1, max_length=MAX_TERMS)


_SHAPE = (
    'Return JSON: {"title": string, "terms": [{"term": string, "definition": string, '
    '"explanation": string, "example": string, "topic": string, "related_terms": [string], '
    '"source_refs": [integer]}]}'
)


def _checked(settings: GeneratorSettings) -> GlossarySettings:
    assert isinstance(settings, GlossarySettings)
    return settings


def term_key(term: str) -> str:
    """Identity of a term: case, spacing and surrounding punctuation do not matter."""
    return _SPACES.sub(" ", term).strip(" .:;,").casefold()


def merge_terms(terms: list[TermOut], source_count: int) -> list[TermOut]:
    """Merge repeated terms into the first occurrence and sort alphabetically. References and
    related terms are unioned; the first definition wins (never concatenated, so it stays one
    faithful definition)."""
    merged: dict[str, TermOut] = {}
    for t in terms:
        t.source_refs = clean_refs(t.source_refs, source_count)
        key = term_key(t.term)
        first = merged.get(key)
        if first is None:
            merged[key] = t
            continue
        first.source_refs = clean_refs([*first.source_refs, *t.source_refs], source_count)
        for rel in t.related_terms:
            if term_key(rel) not in {term_key(r) for r in first.related_terms}:
                first.related_terms.append(rel)
        first.explanation = first.explanation or t.explanation
        first.example = first.example or t.example
        first.topic = first.topic or t.topic
    out = sorted(merged.values(), key=lambda t: term_key(t.term))
    for t in out:  # a term is not related to itself; no repeated related terms
        seen = {term_key(t.term)}
        related: list[str] = []
        for rel in t.related_terms:
            if term_key(rel) not in seen:
                seen.add(term_key(rel))
                related.append(rel)
        t.related_terms = related[:15]
    return out


class GlossaryGenerator(Generator):
    key = "glossary"
    resource_type = "glossary"
    prompt_key = prompts.GLOSSARY_KEY
    settings_model = GlossarySettings
    output_model = GlossaryOutput
    source_mode = "ordered"
    allow_sampled_fallback = True
    min_source_tokens = 20
    max_output_tokens: ClassVar[int | None] = 8000

    def instruction(self, settings: GeneratorSettings) -> str:
        s = _checked(settings)
        return (
            f"TASK\nExtract at most {s.max_terms} important technical terms and define them, in "
            f"{s.language}. Give each term once. "
            + ("Add a short example where the material has one. " if s.include_examples else "")
            + (
                "List related terms that also appear in the material.\n"
                if s.include_related_terms
                else "Leave 'related_terms' empty.\n"
            )
            + _SHAPE
        )

    def title(self, output: Any, settings: GeneratorSettings) -> str:
        return str(output.title)

    def finalize(self, output: Any, source_count: int, settings: GeneratorSettings) -> Any:
        s = _checked(settings)
        terms = merge_terms(output.terms, source_count)
        terms = [
            t for t in terms if t.source_refs
        ]  # a term the material does not support is dropped
        if not terms:
            raise OutputInvalid("terms: no term is supported by a source")
        if len(terms) > s.max_terms:
            raise OutputInvalid("terms: more terms than requested")
        for t in terms:
            if not s.include_examples:
                t.example = ""
            if not s.include_related_terms:
                t.related_terms = []
        output.terms = terms
        return output

    def validate_edit(self, output: Any, source_count: int) -> Any:
        output.terms = merge_terms(output.terms, source_count)
        return output

    def item_count(self, output: Any) -> int:
        return len(output.terms)


def search_terms(
    terms: list[dict[str, Any]],
    query: str | None = None,
    topic: str | None = None,
    descending: bool = False,
) -> list[dict[str, Any]]:
    """Case-insensitive substring search over term, definition and explanation, optional exact
    topic filter, alphabetical order. Pure function over stored material content."""
    needle = (query or "").strip().casefold()
    wanted = (topic or "").strip().casefold()
    found = [
        t
        for t in terms
        if (not wanted or str(t.get("topic", "")).casefold() == wanted)
        and (
            not needle
            or needle
            in " ".join(str(t.get(k, "")) for k in ("term", "definition", "explanation")).casefold()
        )
    ]
    return sorted(found, key=lambda t: term_key(str(t.get("term", ""))), reverse=descending)
