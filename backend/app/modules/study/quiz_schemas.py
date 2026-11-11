"""Quiz API schemas (spec 7.5, 19.4).

Answer-key rule (D-94): every schema used before submission (`QuizOut`, `QuizQuestionOut`,
`AttemptOut`, `AttemptListOut`) has NO field for correct answers, explanations, rubrics or model
answers. Only `ResultQuestionOut`, returned by the results route of a SUBMITTED attempt, does.
"""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

QuestionTypeLiteral = Literal[
    "multiple_choice",
    "multiple_select",
    "true_false",
    "fill_in_the_blank",
    "short_answer",
    "descriptive",
]
Difficulty = Literal["easy", "medium", "hard"]
AnswerFormat = Literal["single_choice", "multiple_choice", "text"]
MAX_ANSWERS_PER_REQUEST = 100


class OptionOut(BaseModel):
    id: str
    text: str


class QuizQuestionOut(BaseModel):
    id: uuid.UUID
    question: str
    question_type: QuestionTypeLiteral
    difficulty: Difficulty
    answer_format: AnswerFormat
    options: list[OptionOut]
    display_order: int


class QuizOut(BaseModel):
    id: uuid.UUID
    study_material_id: uuid.UUID
    title: str
    description: str | None
    time_limit_seconds: int | None
    randomize_order: bool
    question_count: int
    questions: list[QuizQuestionOut]
    created_at: datetime


class QuizResponse(BaseModel):
    success: bool = True
    data: QuizOut


class AttemptOut(BaseModel):
    id: uuid.UUID
    quiz_id: uuid.UUID
    status: Literal["in_progress", "submitted"]
    started_at: datetime
    expires_at: datetime | None
    server_time: datetime
    seconds_remaining: int | None
    submitted_at: datetime | None
    auto_submitted: bool
    question_order: list[uuid.UUID]
    answers: dict[str, Any]
    flagged: list[uuid.UUID]
    # The questions in this attempt's order; empty once submitted (use the results route).
    questions: list[QuizQuestionOut]
    score: float | None
    total_questions: int | None
    graded_questions: int | None
    percentage: float | None


class AttemptResponse(BaseModel):
    success: bool = True
    data: AttemptOut


class AttemptSummary(BaseModel):
    id: uuid.UUID
    status: Literal["in_progress", "submitted"]
    started_at: datetime
    submitted_at: datetime | None
    auto_submitted: bool
    score: float | None
    total_questions: int | None
    graded_questions: int | None
    percentage: float | None


class AttemptListOut(BaseModel):
    items: list[AttemptSummary]
    total: int
    limit: int
    offset: int


class AttemptListResponse(BaseModel):
    success: bool = True
    data: AttemptListOut


ShortText = Annotated[str, Field(max_length=8000)]


class AnswerItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: uuid.UUID
    # Option ids for choice questions, text otherwise. An empty value clears the answer.
    answer: list[Annotated[str, Field(max_length=16)]] | ShortText


class SaveAnswersRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answers: list[AnswerItem] = Field(default_factory=list, max_length=MAX_ANSWERS_PER_REQUEST)
    flagged: list[uuid.UUID] | None = Field(default=None, max_length=MAX_ANSWERS_PER_REQUEST)


class SubmitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Final answers sent with the submit (merged over the saved ones). Optional.
    answers: list[AnswerItem] = Field(default_factory=list, max_length=MAX_ANSWERS_PER_REQUEST)


class ResultQuestionOut(BaseModel):
    """The only schema that carries the answer key; reachable only for a submitted attempt."""

    id: uuid.UUID
    question: str
    question_type: QuestionTypeLiteral
    difficulty: Difficulty
    options: list[OptionOut]
    submitted_answer: list[str] | str | None
    answered: bool
    grading: Literal["auto", "self_assessment"]
    is_correct: bool | None
    awarded_score: float
    # Option ids (choice), accepted answers (fill-in) or the model answer (written questions).
    correct_answers: list[str]
    rubric: list[str]
    explanation: str | None
    source_references: list[dict[str, Any]]


class ResultOut(BaseModel):
    attempt_id: uuid.UUID
    quiz_id: uuid.UUID
    total_questions: int
    graded_questions: int
    correct: int
    incorrect: int
    unanswered: int
    not_graded: int
    score: float
    percentage: float | None
    time_taken_seconds: int
    auto_submitted: bool
    started_at: datetime
    submitted_at: datetime
    note: str
    questions: list[ResultQuestionOut]


class ResultResponse(BaseModel):
    success: bool = True
    data: ResultOut
