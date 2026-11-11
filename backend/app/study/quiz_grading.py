"""Server-side answer validation and grading (spec 7.7, D-94). Pure functions: no I/O.

Objective types are graded here. Short-answer and descriptive questions are NOT auto-graded: they
are reported as `self_assessment` with the model answer and rubric shown after submission.
Multiple-select uses exact-match scoring (no partial credit).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from app.models.quiz import QuizQuestion
from app.study.errors import QuizAnswerInvalidError

CHOICE_TYPES = frozenset({"multiple_choice", "multiple_select", "true_false"})
OBJECTIVE_TYPES = CHOICE_TYPES | {"fill_in_the_blank"}
MAX_TEXT = {"fill_in_the_blank": 500, "short_answer": 2000, "descriptive": 8000}
_SPACES = re.compile(r"\s+")
_EDGE_PUNCT = re.compile(r"^[\W_]+|[\W_]+$")

Answer = list[str] | str


def answer_format(question_type: str) -> str:
    if question_type in ("multiple_choice", "true_false"):
        return "single_choice"
    if question_type == "multiple_select":
        return "multiple_choice"
    return "text"


def normalise_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", value).casefold()
    return _EDGE_PUNCT.sub("", _SPACES.sub(" ", text).strip())


def validate_answer(question: QuizQuestion, answer: Any) -> Answer:
    """The stored form of a submitted answer, or QuizAnswerInvalidError. Empty = unanswered."""
    qtype = question.question_type
    if qtype in CHOICE_TYPES:
        if not isinstance(answer, list) or not all(isinstance(a, str) for a in answer):
            raise QuizAnswerInvalidError
        ids = {o["id"] for o in question.options}
        if len(set(answer)) != len(answer) or any(a not in ids for a in answer):
            raise QuizAnswerInvalidError
        if qtype != "multiple_select" and len(answer) > 1:
            raise QuizAnswerInvalidError
        return sorted(answer)
    if not isinstance(answer, str) or len(answer) > MAX_TEXT[qtype]:
        raise QuizAnswerInvalidError
    return "".join(ch for ch in answer if ch in "\n\t" or ch >= " " and ch != "\x7f").strip()


def is_answered(answer: Any) -> bool:
    return bool(answer)


@dataclass(frozen=True)
class Graded:
    is_correct: bool | None  # None = not auto-graded
    awarded: float
    answered: bool


def grade_question(question: QuizQuestion, answer: Any) -> Graded:
    answered = is_answered(answer)
    qtype = question.question_type
    if qtype not in OBJECTIVE_TYPES:
        return Graded(None, 0.0, answered)
    if not answered:
        return Graded(False, 0.0, False)
    if qtype in CHOICE_TYPES:
        ok = isinstance(answer, list) and set(answer) == set(question.correct_answers)
    else:
        accepted = {normalise_text(a) for a in question.correct_answers}
        ok = isinstance(answer, str) and normalise_text(answer) in accepted
    return Graded(ok, 1.0 if ok else 0.0, True)
