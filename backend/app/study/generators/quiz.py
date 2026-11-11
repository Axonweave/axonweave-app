"""Quiz generator (spec 7): six question types with per-type answer-key validation.

The questions and their answer keys are saved by the engine into `quiz_questions` (D-94). The
material's own content (`dump`) carries only the title and counts, never an answer key, so no
material, version or job endpoint can ever return one.
"""

from __future__ import annotations

import re
from typing import Annotated, Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.ai.prompts import study as prompts
from app.study.generators.base import Generator, GeneratorSettings, OutputInvalid
from app.study.schemas import CleanStr
from app.study.validation import clean_refs, find_near_duplicates

QuestionType = Literal[
    "multiple_choice",
    "multiple_select",
    "true_false",
    "fill_in_the_blank",
    "short_answer",
    "descriptive",
]
QUESTION_TYPES: tuple[str, ...] = (
    "multiple_choice",
    "multiple_select",
    "true_false",
    "fill_in_the_blank",
    "short_answer",
    "descriptive",
)
OBJECTIVE_TYPES = frozenset(
    {"multiple_choice", "multiple_select", "true_false", "fill_in_the_blank"}
)
CHOICE_TYPES = frozenset({"multiple_choice", "multiple_select", "true_false"})
DEFAULT_TYPES: tuple[QuestionType, ...] = (
    "multiple_choice",
    "multiple_select",
    "true_false",
    "fill_in_the_blank",
)
Difficulty = Literal["easy", "medium", "hard"]
MAX_QUESTIONS = 50
MAX_QUESTION = 800
MAX_OPTION = 300
MAX_EXPLANATION = 1500
MAX_BLANK_ANSWER = 120
MAX_MODEL_ANSWER = 3000
MAX_RUBRIC_ITEM = 300
BLANK = "___"
TRUE_FALSE_OPTIONS = [{"id": "true", "text": "True"}, {"id": "false", "text": "False"}]
_OPTION_ID = re.compile(r"^[A-F]$")


class QuizSettings(GeneratorSettings):
    count: int = Field(default=10, ge=1, le=MAX_QUESTIONS)
    question_types: list[QuestionType] = Field(
        default_factory=lambda: list(DEFAULT_TYPES), min_length=1, max_length=6
    )
    difficulty: Literal["easy", "medium", "hard", "mixed"] = "mixed"
    time_limit_minutes: int | None = Field(default=None, ge=1, le=300)
    randomize_order: bool = False
    # Explanations are only ever shown after submission (D-94); "immediately" is not offered.
    show_explanations: Literal["after_submission"] = "after_submission"

    def model_post_init(self, __context: Any) -> None:
        # canonical order and no repeats, so equal requests have equal fingerprints
        self.question_types = [t for t in QUESTION_TYPES if t in self.question_types]  # type: ignore[misc]


class OptionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: Annotated[str, Field(pattern=r"^[A-F]$")]
    text: Annotated[CleanStr, Field(min_length=1, max_length=MAX_OPTION)]


class QuestionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: Annotated[CleanStr, Field(min_length=10, max_length=MAX_QUESTION)]
    question_type: QuestionType
    difficulty: Difficulty
    options: list[OptionOut] = Field(default_factory=list, max_length=6)
    correct_answers: list[Annotated[CleanStr, Field(min_length=1, max_length=MAX_MODEL_ANSWER)]] = (
        Field(min_length=1, max_length=6)
    )
    explanation: Annotated[CleanStr, Field(max_length=MAX_EXPLANATION)] = ""
    rubric: list[Annotated[CleanStr, Field(min_length=1, max_length=MAX_RUBRIC_ITEM)]] = Field(
        default_factory=list, max_length=8
    )
    source_refs: list[int] = Field(default_factory=list, max_length=20)


class QuizOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Annotated[CleanStr, Field(min_length=1, max_length=200)]
    description: Annotated[CleanStr, Field(max_length=1000)] = ""
    questions: list[QuestionOut] = Field(min_length=1, max_length=MAX_QUESTIONS)


_TYPE_TEXT = {
    "multiple_choice": "multiple_choice (3 to 6 options labelled A, B, C...; exactly ONE correct)",
    "multiple_select": (
        "multiple_select (4 to 6 options; TWO OR MORE correct but not all; the question must say "
        "to select all that apply)"
    ),
    "true_false": 'true_false (a statement; no options; correct_answers is ["true"] or ["false"])',
    "fill_in_the_blank": (
        f"fill_in_the_blank (one sentence with the missing term replaced by {BLANK}; no options; "
        "correct_answers lists the accepted spellings, short)"
    ),
    "short_answer": (
        "short_answer (no options; correct_answers has ONE concise model answer; rubric lists "
        "1 to 6 marking points)"
    ),
    "descriptive": (
        "descriptive (no options; correct_answers has ONE model answer of a few sentences; "
        "rubric lists 2 to 8 marking points)"
    ),
}
_SHAPE = (
    'Return JSON: {"title": string, "description": string, "questions": [{"question": string, '
    '"question_type": string, "difficulty": "easy" | "medium" | "hard", "options": [{"id": '
    '"A", "text": string}], "correct_answers": [string], "explanation": string, "rubric": '
    '[string], "source_refs": [integer]}]}. For choice questions correct_answers holds option ids.'
)


def _checked(settings: GeneratorSettings) -> QuizSettings:
    assert isinstance(settings, QuizSettings)
    return settings


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def question_rules(i: int, q: QuestionOut) -> None:
    """Per-type answer-key rules. Raises OutputInvalid naming only the path and the rule."""
    where = f"questions.{i}"
    answers = q.correct_answers
    if q.question_type in CHOICE_TYPES and not q.explanation:
        raise OutputInvalid(f"{where}: explanation is required")
    if q.question_type in ("multiple_choice", "multiple_select"):
        ids = [o.id for o in q.options]
        if not 3 <= len(ids) <= 6 or (q.question_type == "multiple_select" and len(ids) < 4):
            raise OutputInvalid(f"{where}: wrong number of options")
        if len(set(ids)) != len(ids):
            raise OutputInvalid(f"{where}: duplicate option ids")
        if len({_norm(o.text) for o in q.options}) != len(q.options):
            raise OutputInvalid(f"{where}: duplicate option text")
        if len(set(answers)) != len(answers) or any(a not in ids for a in answers):
            raise OutputInvalid(f"{where}: correct answer is not an option")
        if q.question_type == "multiple_choice" and len(answers) != 1:
            raise OutputInvalid(f"{where}: multiple choice needs exactly one correct option")
        if q.question_type == "multiple_select" and not 2 <= len(answers) < len(ids):
            raise OutputInvalid(f"{where}: multiple select needs 2 or more but not all correct")
        if any(len(a) != 1 or not _OPTION_ID.match(a) for a in answers):
            raise OutputInvalid(f"{where}: malformed answer key")
    elif q.question_type == "true_false":
        if q.options:
            raise OutputInvalid(f"{where}: true/false has no options")
        if len(answers) != 1 or answers[0] not in ("true", "false"):
            raise OutputInvalid(f"{where}: true/false answer must be true or false")
    elif q.question_type == "fill_in_the_blank":
        if q.options:
            raise OutputInvalid(f"{where}: fill-in-the-blank has no options")
        if q.question.count(BLANK) != 1:
            raise OutputInvalid(f"{where}: fill-in-the-blank needs exactly one blank")
        if any(len(a) > MAX_BLANK_ANSWER for a in answers):
            raise OutputInvalid(f"{where}: fill-in-the-blank answer too long")
        if any(len(_norm(a)) >= 4 and _norm(a) in _norm(q.question) for a in answers):
            raise OutputInvalid(f"{where}: the question gives away its answer")
    else:  # short_answer, descriptive
        if q.options:
            raise OutputInvalid(f"{where}: written question has no options")
        if len(answers) != 1:
            raise OutputInvalid(f"{where}: needs exactly one model answer")
        low = 1 if q.question_type == "short_answer" else 2
        high = 6 if q.question_type == "short_answer" else 8
        if not low <= len(q.rubric) <= high:
            raise OutputInvalid(f"{where}: wrong number of rubric points")
    if q.question_type not in ("short_answer", "descriptive") and q.rubric:
        q.rubric = []


class QuizGenerator(Generator):
    key = "quiz"
    resource_type = "quiz"
    prompt_key = prompts.QUIZ_KEY
    settings_model = QuizSettings
    output_model = QuizOutput
    source_mode = "ordered"
    allow_sampled_fallback = True
    min_source_tokens = 20
    max_output_tokens: ClassVar[int | None] = 8000
    item_store = True

    def instruction(self, settings: GeneratorSettings) -> str:
        s = _checked(settings)
        kinds = "; ".join(_TYPE_TEXT[t] for t in s.question_types)
        level = "a mix of easy, medium and hard" if s.difficulty == "mixed" else s.difficulty
        return (
            f"TASK\nWrite at most {s.count} quiz questions, in {s.language}. Allowed types: "
            f"{kinds}. Difficulty: {level}; difficulty is the thinking the question demands, not "
            "its length. Give every choice question plausible distractors and a short "
            "explanation of the correct answer.\n" + _SHAPE
        )

    def title(self, output: Any, settings: GeneratorSettings) -> str:
        return str(output.title)

    def finalize(self, output: Any, source_count: int, settings: GeneratorSettings) -> Any:
        s = _checked(settings)
        if len(output.questions) > s.count:
            raise OutputInvalid("questions: more questions than requested")
        kept: list[QuestionOut] = []
        for i, q in enumerate(output.questions):
            question_rules(i, q)
            if q.question_type not in s.question_types:
                raise OutputInvalid(f"questions.{i}: question type not requested")
            if s.difficulty != "mixed" and q.difficulty != s.difficulty:
                raise OutputInvalid(f"questions.{i}: wrong difficulty")
            q.source_refs = clean_refs(q.source_refs, source_count)
            if not q.source_refs:
                continue  # not tied to the material: unsupported, so not kept
            kept.append(q)
        if not kept:
            raise OutputInvalid("questions: no question is supported by a source")
        if find_near_duplicates([q.question for q in kept]):
            raise OutputInvalid("questions: duplicate or near-duplicate questions")
        output.questions = kept
        return output

    def item_count(self, output: Any) -> int:
        return len(output.questions)

    def dump(self, output: Any) -> dict[str, Any]:
        """The stored material content. Deliberately WITHOUT the questions: the answer key lives
        only in `quiz_questions` and is read only by grading and submitted results (D-94)."""
        return {
            "title": output.title,
            "description": output.description,
            "question_count": len(output.questions),
            "question_types": sorted({q.question_type for q in output.questions}),
        }
