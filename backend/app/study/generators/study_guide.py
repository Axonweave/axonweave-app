"""Study guide generator (spec 8): topic hierarchy, learning objectives, source attribution.

Objectives the material does not support are kept only when clearly marked as generated
recommendations (8.4). Practice questions are questions only, never answers.
"""

from __future__ import annotations

from typing import Annotated, Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.ai.prompts import study as prompts
from app.study.generators.base import Generator, GeneratorSettings, OutputInvalid
from app.study.schemas import CleanStr
from app.study.validation import clean_refs, find_duplicates

GuideLevel = Literal["beginner", "intermediate", "advanced"]
GuideFocus = Literal["exam_preparation", "conceptual_understanding", "practical_application"]
MAX_SECTIONS = 40
MAX_OBJECTIVES = 12


class StudyGuideSettings(GeneratorSettings):
    level: GuideLevel = "intermediate"
    focus: GuideFocus = "conceptual_understanding"
    max_sections: int = Field(default=15, ge=3, le=MAX_SECTIONS)
    include_objectives: bool = True
    include_prerequisites: bool = True
    include_examples: bool = True
    include_practice_questions: bool = True
    include_source_references: bool = True


class ObjectiveOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: Annotated[CleanStr, Field(min_length=3, max_length=400)]
    generated_recommendation: bool = False
    source_refs: list[int] = Field(default_factory=list, max_length=20)


class GuideSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    heading: Annotated[CleanStr, Field(min_length=1, max_length=200)]
    level: Annotated[int, Field(ge=1, le=3)] = 1
    body: Annotated[CleanStr, Field(max_length=6000)] = ""
    bullets: list[Annotated[CleanStr, Field(min_length=1, max_length=600)]] = Field(
        default_factory=list, max_length=30
    )
    source_refs: list[int] = Field(default_factory=list, max_length=30)


class PracticeQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: Annotated[CleanStr, Field(min_length=5, max_length=500)]
    source_refs: list[int] = Field(default_factory=list, max_length=20)


class StudyGuideOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Annotated[CleanStr, Field(min_length=1, max_length=200)]
    overview: Annotated[CleanStr, Field(max_length=3000)] = ""
    learning_objectives: list[ObjectiveOut] = Field(default_factory=list, max_length=MAX_OBJECTIVES)
    prerequisites: list[Annotated[CleanStr, Field(min_length=1, max_length=300)]] = Field(
        default_factory=list, max_length=15
    )
    sections: list[GuideSection] = Field(min_length=1, max_length=MAX_SECTIONS)
    key_takeaways: list[Annotated[CleanStr, Field(min_length=1, max_length=500)]] = Field(
        default_factory=list, max_length=20
    )
    practice_questions: list[PracticeQuestion] = Field(default_factory=list, max_length=20)


_SHAPE = (
    'Return JSON: {"title": string, "overview": string, "learning_objectives": [{"text": '
    'string, "generated_recommendation": boolean, "source_refs": [integer]}], "prerequisites": '
    '[string], "sections": [{"heading": string, "level": 1 | 2 | 3, "body": string, "bullets": '
    '[string], "source_refs": [integer]}], "key_takeaways": [string], "practice_questions": '
    '[{"question": string, "source_refs": [integer]}]}'
)
_FOCUS_TEXT = {
    "exam_preparation": "Emphasise what is worth revising: definitions, comparisons and processes",
    "conceptual_understanding": "Emphasise why and how things work",
    "practical_application": "Emphasise how to apply the concepts",
}


def _checked(settings: GeneratorSettings) -> StudyGuideSettings:
    assert isinstance(settings, StudyGuideSettings)
    return settings


def check_hierarchy(sections: list[GuideSection]) -> None:
    """Heading hierarchy (8.4): start at level 1, never skip a level going deeper."""
    previous = 0
    for i, sec in enumerate(sections):
        if sec.level > previous + 1:
            raise OutputInvalid(f"sections.{i}: heading level skips a level")
        if not sec.body and not sec.bullets:
            raise OutputInvalid(f"sections.{i}: empty section")
        previous = sec.level
    if find_duplicates([sec.heading for sec in sections]):
        raise OutputInvalid("sections: duplicate headings")


def clean_guide(output: Any, source_count: int) -> None:
    for sec in output.sections:
        sec.source_refs = clean_refs(sec.source_refs, source_count)
    for q in output.practice_questions:
        q.source_refs = clean_refs(q.source_refs, source_count)
    for obj in output.learning_objectives:
        obj.source_refs = clean_refs(obj.source_refs, source_count)
        if not obj.source_refs:  # unsupported: must be visibly a generated recommendation
            obj.generated_recommendation = True


class StudyGuideGenerator(Generator):
    key = "study_guide"
    resource_type = "study_guide"
    prompt_key = prompts.STUDY_GUIDE_KEY
    settings_model = StudyGuideSettings
    output_model = StudyGuideOutput
    source_mode = "ordered"
    allow_sampled_fallback = True
    min_source_tokens = 20
    max_output_tokens: ClassVar[int | None] = 8000

    def instruction(self, settings: GeneratorSettings) -> str:
        s = _checked(settings)
        return (
            f"TASK\nWrite a {s.level}-level study guide, in {s.language}. {_FOCUS_TEXT[s.focus]}. "
            f"Use at most {s.max_sections} sections in a heading hierarchy (level 1 topics, level "
            "2 subtopics, level 3 details). "
            + (
                "Include learning objectives. "
                if s.include_objectives
                else "Leave 'learning_objectives' empty. "
            )
            + (
                "List prerequisite concepts. "
                if s.include_prerequisites
                else "Leave 'prerequisites' empty. "
            )
            + ("Include examples from the material. " if s.include_examples else "")
            + (
                "End with practice questions (questions only, no answers).\n"
                if s.include_practice_questions
                else "Leave 'practice_questions' empty.\n"
            )
            + _SHAPE
        )

    def title(self, output: Any, settings: GeneratorSettings) -> str:
        return str(output.title)

    def finalize(self, output: Any, source_count: int, settings: GeneratorSettings) -> Any:
        s = _checked(settings)
        if len(output.sections) > s.max_sections:
            raise OutputInvalid("sections: more sections than allowed")
        check_hierarchy(output.sections)
        clean_guide(output, source_count)
        if not any(sec.source_refs for sec in output.sections):
            raise OutputInvalid("sections: no section is supported by a source")
        if not s.include_objectives:
            output.learning_objectives = []
        if not s.include_prerequisites:
            output.prerequisites = []
        if not s.include_practice_questions:
            output.practice_questions = []
        if not s.include_source_references:
            for item in (*output.sections, *output.learning_objectives, *output.practice_questions):
                item.source_refs = []
        return output

    def validate_edit(self, output: Any, source_count: int) -> Any:
        check_hierarchy(output.sections)
        clean_guide(output, source_count)
        return output

    def item_count(self, output: Any) -> int:
        return len(output.sections)
