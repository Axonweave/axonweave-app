"""The engine proof generator (M0). It produces a short list of statements from the material and
exists only to exercise every engine path (reading, prompting, structured output, validation,
correction, saving, jobs, quotas, usage). It is refused when APP_ENV=production (D-90)."""

from __future__ import annotations

from typing import Annotated, Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.ai.prompts import study as prompts
from app.study.generators.base import Generator, GeneratorSettings, OutputInvalid
from app.study.schemas import CleanStr
from app.study.validation import clean_refs, find_duplicates

Difficulty = Literal["easy", "medium", "hard"]
MAX_ITEMS = 10


class EchoSettings(GeneratorSettings):
    item_count: int = Field(default=3, ge=1, le=MAX_ITEMS)
    difficulty: Difficulty = "medium"


class EchoItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: Annotated[CleanStr, Field(min_length=1, max_length=400)]
    difficulty: Difficulty
    source_refs: list[int] = Field(default_factory=list, max_length=20)


class EchoOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Annotated[CleanStr, Field(min_length=1, max_length=200)]
    items: list[EchoItem] = Field(min_length=1, max_length=MAX_ITEMS)


class EchoGenerator(Generator):
    key = "echo"
    resource_type = "echo"
    prompt_key = prompts.ECHO_KEY
    settings_model = EchoSettings
    output_model = EchoOutput
    source_mode = "ordered"
    allow_sampled_fallback = True
    max_output_tokens: ClassVar[int | None] = 1500
    test_only = True

    def instruction(self, settings: GeneratorSettings) -> str:
        assert isinstance(settings, EchoSettings)
        return (
            f"TASK\nWrite {settings.item_count} short statements taken from the reference "
            "material, "
            f"in {settings.language}, at {settings.difficulty} difficulty.\n"
            'Return JSON: {"title": string, "items": [{"text": string, '
            '"difficulty": "easy" | "medium" | "hard", "source_refs": [integer]}]}'
        )

    def title(self, output: Any, settings: GeneratorSettings) -> str:
        return str(output.title)

    def finalize(self, output: Any, source_count: int, settings: GeneratorSettings) -> Any:
        assert isinstance(settings, EchoSettings)
        if len(output.items) > settings.item_count:
            raise OutputInvalid("items: more items than requested")
        dupes = find_duplicates([i.text for i in output.items])
        if dupes:
            raise OutputInvalid("items: duplicate statements")
        for item in output.items:
            item.source_refs = clean_refs(item.source_refs, source_count)
        return output

    def item_count(self, output: Any) -> int:
        return len(output.items)
