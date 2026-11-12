"""Pure helpers for AI-assisted grading of written answers (Phase 5 M1, D-112).

No I/O here: building the grading turn and validating the model's reply. The student's answer, the
reference answer and the rubric are untrusted DATA inside escaped blocks; the rules live in the
system prompt. The reply is validated by a Pydantic model and the score is clamped to [0, 1], so a
model that is talked into "100%" by the answer text cannot return more than a full mark, and a
malformed reply is never turned into a silent 0 (the caller marks the answer pending instead).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.models.quiz import QuizQuestion
from app.study.generators.base import OutputInvalid
from app.study.validation import describe_errors, parse_json_object

AI_GRADED_TYPES = frozenset({"short_answer", "descriptive"})
MAX_POINTS = 8
MAX_POINT_CHARS = 300
MAX_EXPLANATION_CHARS = 600

# JSON schema handed to providers that support structured output.
GRADE_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "score": {"type": "number"},
        "explanation": {"type": "string"},
        "covered_points": {"type": "array", "items": {"type": "string"}},
        "missing_points": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["score", "explanation", "covered_points", "missing_points"],
}


class GradeOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    score: float
    explanation: str = Field(default="", max_length=4000)
    covered_points: list[str] = Field(default_factory=list, max_length=50)
    missing_points: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("score")
    @classmethod
    def _finite(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("score must be a finite number")
        return v


@dataclass(frozen=True)
class GradeResult:
    fraction: float  # 0..1, two decimals
    explanation: str
    covered_points: list[str]
    missing_points: list[str]

    def detail(self) -> dict[str, object]:
        """What is stored in `quiz_attempt_answers.evaluation_detail`: the grader's own words only
        (never the reference answer or the rubric text)."""
        return {
            "explanation": self.explanation,
            "covered_points": self.covered_points,
            "missing_points": self.missing_points,
        }


def _escape(text: str) -> str:
    """Neutralise anything that could close or fake one of our data blocks."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def grading_turn(question: QuizQuestion, answer: str) -> str:
    reference = "\n".join(_escape(a) for a in question.correct_answers) or "(none stored)"
    rubric = "\n".join(f"- {_escape(r)}" for r in question.rubric) or "(none stored)"
    return (
        "Grade the student's answer to the question below.\n\n"
        f"<question>\n{_escape(question.question)}\n</question>\n\n"
        f"<reference_answer>\n{reference}\n</reference_answer>\n\n"
        f"<rubric>\n{rubric}\n</rubric>\n\n"
        f"<student_answer>\n{_escape(answer)}\n</student_answer>\n\n"
        'Reply with the JSON object only: {"score": 0-1, "explanation": "...", '
        '"covered_points": [...], "missing_points": [...]}.'
    )


def _clean_points(points: list[str]) -> list[str]:
    cleaned = [p.strip()[:MAX_POINT_CHARS] for p in points if isinstance(p, str) and p.strip()]
    return cleaned[:MAX_POINTS]


def parse_grade(raw: str) -> GradeResult:
    """Validate the model's reply or raise OutputInvalid (caller makes one correction call)."""
    data = parse_json_object(raw)
    if "score" not in data:
        raise OutputInvalid("score: field required")
    try:
        parsed = GradeOut.model_validate(data)
    except ValidationError as exc:
        raise OutputInvalid(describe_errors(exc)) from None
    fraction = min(1.0, max(0.0, parsed.score))
    return GradeResult(
        fraction=round(fraction, 2),
        explanation=parsed.explanation.strip()[:MAX_EXPLANATION_CHARS],
        covered_points=_clean_points(parsed.covered_points),
        missing_points=_clean_points(parsed.missing_points),
    )
