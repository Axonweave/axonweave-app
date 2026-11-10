"""Summary generator (spec 5): six types, structured sections, validated source references.

A long chapter does not fit one prompt, so the engine runs ordered map-reduce for this generator
(`map_reduce = True`): every chunk reaches a map step in reading order, and the reducer sees the
notes of every batch. The result reports exactly which sources were included.
"""

from __future__ import annotations

from typing import Annotated, Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.ai.prompts import study as prompts
from app.study.generators.base import Generator, GeneratorSettings, OutputInvalid
from app.study.schemas import CleanStr
from app.study.validation import clean_refs, find_duplicates

SummaryType = Literal[
    "quick", "detailed", "section_wise", "exam_oriented", "beginner_friendly", "key_point"
]
DetailLevel = Literal["brief", "standard", "detailed"]
SectionKind = Literal[
    "overview",
    "concept",
    "definition",
    "process",
    "comparison",
    "example",
    "formula",
    "takeaway",
    "other",
]
MAX_SECTIONS = 40
_MAX_SECTIONS = {
    ("quick", "brief"): 3,
    ("quick", "standard"): 5,
    ("quick", "detailed"): 6,
    ("key_point", "brief"): 4,
    ("key_point", "standard"): 8,
    ("key_point", "detailed"): 12,
}


class SummarySettings(GeneratorSettings):
    summary_type: SummaryType = "detailed"
    detail_level: DetailLevel = "standard"
    include_examples: bool = False
    include_definitions: bool = True
    include_important_terms: bool = True
    include_formulas: bool = False
    preserve_headings: bool = True
    include_source_references: bool = True


class SummarySection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    heading: Annotated[CleanStr, Field(min_length=1, max_length=200)]
    kind: SectionKind = "concept"
    body: Annotated[CleanStr, Field(max_length=6000)] = ""
    bullets: list[Annotated[CleanStr, Field(min_length=1, max_length=600)]] = Field(
        default_factory=list, max_length=30
    )
    additional_explanation: bool = False
    source_refs: list[int] = Field(default_factory=list, max_length=30)


class SummaryOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Annotated[CleanStr, Field(min_length=1, max_length=200)]
    sections: list[SummarySection] = Field(min_length=1, max_length=MAX_SECTIONS)


class SummaryNote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: Annotated[CleanStr, Field(min_length=1, max_length=4000)]
    source_refs: list[int] = Field(default_factory=list, max_length=30)


class SummaryNotes(BaseModel):
    """Intermediate map/condense output."""

    model_config = ConfigDict(extra="forbid")

    notes: list[SummaryNote] = Field(min_length=1, max_length=60)


_TYPE_TEXT: dict[str, str] = {
    "quick": "a QUICK summary: a short overview of the main ideas only",
    "detailed": (
        "a DETAILED summary: structured and comprehensive; adapt the sections to the material "
        "(introduction, main concepts, explanations, processes, comparisons, takeaways)"
    ),
    "section_wise": (
        "a SECTION-WISE summary: one section per heading or section of the original, in the "
        "original order"
    ),
    "exam_oriented": (
        "an EXAM-ORIENTED summary: important definitions, key concepts, comparisons, processes "
        "and formulas that are worth revising. Do not claim any topic will appear in an exam"
    ),
    "beginner_friendly": (
        "a BEGINNER-FRIENDLY summary: simple language, short sentences and examples; keep "
        "technical terms but explain them"
    ),
    "key_point": "a KEY-POINT summary: concise bullet points only (leave 'body' empty)",
}
_LENGTH = {
    "brief": "Keep it short.",
    "standard": "Use a moderate length.",
    "detailed": "Be thorough.",
}
_SHAPE = (
    'Return JSON: {"title": string, "sections": [{"heading": string, "kind": "overview" | '
    '"concept" | "definition" | "process" | "comparison" | "example" | "formula" | "takeaway" '
    '| "other", "body": string, "bullets": [string], "additional_explanation": boolean, '
    '"source_refs": [integer]}]}'
)


def _checked(settings: GeneratorSettings) -> SummarySettings:
    assert isinstance(settings, SummarySettings)
    return settings


def _toggles(s: SummarySettings) -> str:
    lines = [
        "Include examples from the material." if s.include_examples else "Omit examples.",
        "Include important definitions."
        if s.include_definitions
        else "Do not add a definitions section.",
        "List the important terms." if s.include_important_terms else "Do not list terms.",
        "Include formulas that appear in the material." if s.include_formulas else "Omit formulas.",
        "Use the original headings and section order where the material has them."
        if s.preserve_headings
        else "Organise the sections freely.",
    ]
    return " ".join(lines)


class SummaryGenerator(Generator):
    key = "summary"
    resource_type = "summary"
    prompt_key = prompts.SUMMARY_KEY
    notes_prompt_key = prompts.SUMMARY_NOTES_KEY
    settings_model = SummarySettings
    output_model = SummaryOutput
    notes_model = SummaryNotes
    source_mode = "ordered"
    map_reduce = True
    min_source_tokens = 20
    max_output_tokens: ClassVar[int | None] = 8000

    def instruction(self, settings: GeneratorSettings) -> str:
        s = _checked(settings)
        cap = _MAX_SECTIONS.get((s.summary_type, s.detail_level), MAX_SECTIONS)
        return (
            f"TASK\nWrite {_TYPE_TEXT[s.summary_type]}, in {s.language}. {_LENGTH[s.detail_level]} "
            f"Use at most {cap} sections. {_toggles(s)}\n{_SHAPE}"
        )

    def section_instruction(self, settings: GeneratorSettings, heading: str) -> str:
        s = _checked(settings)
        return (
            f"TASK\nRewrite ONE section of {_TYPE_TEXT[s.summary_type]}, in {s.language}. "
            f"The section is titled {heading!r}; use only the passages that concern it. "
            f"{_toggles(s)}\n{_SHAPE}\nReturn exactly one section in 'sections'."
        )

    def notes_instruction(self, settings: GeneratorSettings) -> str:
        s = _checked(settings)
        return (
            f"TASK\nCondense the material below into working notes in {s.language}. "
            f"Later they become {_TYPE_TEXT[s.summary_type]}.\n"
            'Return JSON: {"notes": [{"text": string, "source_refs": [integer]}]}'
        )

    def reduce_instruction(self, settings: GeneratorSettings) -> str:
        return (
            self.instruction(settings)
            + "\nThe reference material is a numbered list of notes in reading order, each with "
            "its source numbers. Cover every note's content. Cite with those source numbers."
        )

    def title(self, output: Any, settings: GeneratorSettings) -> str:
        return str(output.title)

    def finalize(self, output: Any, source_count: int, settings: GeneratorSettings) -> Any:
        s = _checked(settings)
        cap = _MAX_SECTIONS.get((s.summary_type, s.detail_level), MAX_SECTIONS)
        if len(output.sections) > cap:
            raise OutputInvalid("sections: more sections than allowed")
        for i, sec in enumerate(output.sections):
            if not sec.body and not sec.bullets:
                raise OutputInvalid(f"sections.{i}: empty section")
        if find_duplicates([sec.heading for sec in output.sections]):
            raise OutputInvalid("sections: duplicate headings")
        for sec in output.sections:
            sec.source_refs = (
                clean_refs(sec.source_refs, source_count) if s.include_source_references else []
            )
        return output

    def validate_edit(self, output: Any, source_count: int) -> Any:
        for i, sec in enumerate(output.sections):
            if not sec.body and not sec.bullets:
                raise OutputInvalid(f"sections.{i}: empty section")
        if find_duplicates([sec.heading for sec in output.sections]):
            raise OutputInvalid("sections: duplicate headings")
        for sec in output.sections:
            sec.source_refs = clean_refs(sec.source_refs, source_count)
        return output

    def item_count(self, output: Any) -> int:
        return len(output.sections)
