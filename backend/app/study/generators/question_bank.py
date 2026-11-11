"""Question bank generator (spec 11): reusable questions organised by topic and difficulty.

Questions share the M3 validation (`question_rules`) and storage: the answer keys live only in
`quiz_questions` (a quiz row owned by the material, D-94), so the bank can be practised and turned
into quizzes later. The material's own content is the PUBLIC view: question text, options, type,
difficulty, topic and source references, never a key, explanation or rubric.
"""

from __future__ import annotations

from typing import Annotated, Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.ai.prompts import study as prompts
from app.study.generators.base import Generator, GeneratorSettings, OutputInvalid
from app.study.generators.quiz import (
    _TYPE_TEXT,
    DEFAULT_TYPES,
    MAX_QUESTIONS,
    QUESTION_TYPES,
    QuestionOut,
    QuestionType,
    question_rules,
)
from app.study.schemas import CleanStr
from app.study.validation import clean_refs, find_near_duplicates

DEFAULT_TOPIC = "General"
DIFFICULTIES = ("easy", "medium", "hard")


class QuestionBankSettings(GeneratorSettings):
    count: int = Field(default=20, ge=1, le=MAX_QUESTIONS)
    question_types: list[QuestionType] = Field(
        default_factory=lambda: list(DEFAULT_TYPES), min_length=1, max_length=6
    )
    difficulty: Literal["easy", "medium", "hard", "mixed"] = "mixed"

    def model_post_init(self, __context: Any) -> None:
        self.question_types = [t for t in QUESTION_TYPES if t in self.question_types]  # type: ignore[misc]


class BankQuestionOut(QuestionOut):
    topic: Annotated[CleanStr, Field(max_length=120)] = ""


class QuestionBankOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Annotated[CleanStr, Field(min_length=1, max_length=200)]
    questions: list[BankQuestionOut] = Field(min_length=1, max_length=MAX_QUESTIONS)


_SHAPE = (
    'Return JSON: {"title": string, "questions": [{"question": string, "question_type": '
    'string, "difficulty": "easy" | "medium" | "hard", "topic": string, "options": [{"id": '
    '"A", "text": string}], "correct_answers": [string], "explanation": string, "rubric": '
    '[string], "source_refs": [integer]}]}. For choice questions correct_answers holds option ids.'
)


def _checked(settings: GeneratorSettings) -> QuestionBankSettings:
    assert isinstance(settings, QuestionBankSettings)
    return settings


def organise(questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group by topic, then difficulty (11.3). Entries carry the question's position `index`."""
    topics: dict[str, dict[str, list[int]]] = {}
    for i, q in enumerate(questions):
        by_diff = topics.setdefault(str(q["topic"]), {d: [] for d in DIFFICULTIES})
        by_diff[str(q["difficulty"])].append(i)
    return [
        {"topic": topic, "difficulty": {d: idx for d, idx in by_diff.items() if idx}}
        for topic, by_diff in sorted(topics.items(), key=lambda kv: kv[0].casefold())
    ]


class QuestionBankGenerator(Generator):
    key = "question_bank"
    resource_type = "question_bank"
    prompt_key = prompts.QUESTION_BANK_KEY
    settings_model = QuestionBankSettings
    output_model = QuestionBankOutput
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
            f"TASK\nWrite at most {s.count} reusable questions, in {s.language}. Allowed types: "
            f"{kinds}. Difficulty: {level}. Give every question a short 'topic' label from the "
            "material (reuse the same label for questions on the same topic) and every choice "
            "question plausible distractors and a short explanation.\n" + _SHAPE
        )

    def title(self, output: Any, settings: GeneratorSettings) -> str:
        return str(output.title)

    def finalize(self, output: Any, source_count: int, settings: GeneratorSettings) -> Any:
        s = _checked(settings)
        if len(output.questions) > s.count:
            raise OutputInvalid("questions: more questions than requested")
        kept: list[BankQuestionOut] = []
        for i, q in enumerate(output.questions):
            question_rules(i, q)
            if q.question_type not in s.question_types:
                raise OutputInvalid(f"questions.{i}: question type not requested")
            if s.difficulty != "mixed" and q.difficulty != s.difficulty:
                raise OutputInvalid(f"questions.{i}: wrong difficulty")
            q.source_refs = clean_refs(q.source_refs, source_count)
            if not q.source_refs:
                continue  # not tied to the material: unsupported, so not kept
            q.topic = q.topic or DEFAULT_TOPIC
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
        """The public view only (D-94, spec 21.4): no correct_answers, explanation or rubric."""
        questions = [
            {
                "index": i,
                "question": q.question,
                "question_type": q.question_type,
                "difficulty": q.difficulty,
                "topic": q.topic or DEFAULT_TOPIC,
                "options": [o.model_dump() for o in q.options],
                "source_refs": list(q.source_refs),
                "origin": "generated",
            }
            for i, q in enumerate(output.questions)
        ]
        return {
            "title": output.title,
            "question_count": len(questions),
            "questions": questions,
            "organisation": organise(questions),
        }
