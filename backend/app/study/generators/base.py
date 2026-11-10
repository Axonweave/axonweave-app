"""Generator contract. A generator declares WHAT to produce; the engine does everything else
(source reading, prompting, provider call, validation, correction, saving, jobs, usage)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict

SourceMode = Literal["ordered", "sampled", "retrieved"]


class GeneratorSettings(BaseModel):
    """Base for per-generator settings. Unknown fields are rejected (422), never ignored."""

    model_config = ConfigDict(extra="forbid")

    language: str = "English"


class OutputInvalid(ValueError):
    """The model output broke a rule. The message lists field paths and rule names only, never the
    output itself, so it is safe to log and to send back in the one correction attempt."""


class Generator(ABC):
    key: ClassVar[str]  # request value, e.g. "summary"
    resource_type: ClassVar[str]  # study_materials.resource_type
    prompt_key: ClassVar[str]  # prompt registry key
    settings_model: ClassVar[type[GeneratorSettings]]
    output_model: ClassVar[type[BaseModel]]
    source_mode: ClassVar[SourceMode] = "ordered"
    #: When the scope is larger than the input budget: sample it (True) or refuse (False).
    allow_sampled_fallback: ClassVar[bool] = False
    #: Output token cap for this generator (also capped by STUDY_MAX_OUTPUT_TOKENS, the model).
    max_output_tokens: ClassVar[int | None] = None
    #: Long scopes are summarised in ordered batches (map-reduce) instead of refused or sampled.
    map_reduce: ClassVar[bool] = False
    #: Refuse a source thinner than this many estimated tokens (0 = no minimum).
    min_source_tokens: ClassVar[int] = 0
    #: Only in development/testing (the engine proof generator).
    test_only: ClassVar[bool] = False

    @abstractmethod
    def instruction(self, settings: GeneratorSettings) -> str:
        """The TASK block: what to produce and the exact JSON shape (from validated settings)."""

    # Map-reduce and section regeneration hooks (generators that set `map_reduce` implement them).
    notes_prompt_key: ClassVar[str] = ""
    notes_model: ClassVar[type[BaseModel] | None] = None

    def notes_instruction(self, settings: GeneratorSettings) -> str:
        raise NotImplementedError

    def reduce_instruction(self, settings: GeneratorSettings) -> str:
        raise NotImplementedError

    def section_instruction(self, settings: GeneratorSettings, heading: str) -> str:
        raise NotImplementedError

    def validate_edit(self, output: Any, source_count: int) -> Any:
        """Checks for content the USER edited. Unlike `finalize` this has no generation caps; it
        only keeps the resource valid and its source references real."""
        return output

    @abstractmethod
    def title(self, output: Any, settings: GeneratorSettings) -> str: ...

    @abstractmethod
    def finalize(self, output: Any, source_count: int, settings: GeneratorSettings) -> Any:
        """Semantic checks the schema cannot express (duplicates, counts) and source reference
        clean-up. Strip invalid source numbers; raise OutputInvalid for anything else wrong."""

    def retrieval_query(self, settings: GeneratorSettings) -> str:
        """Only for source_mode == "retrieved"."""
        return ""

    @abstractmethod
    def item_count(self, output: Any) -> int: ...

    def dump(self, output: Any) -> dict[str, Any]:
        result: dict[str, Any] = output.model_dump(mode="json")
        return result
