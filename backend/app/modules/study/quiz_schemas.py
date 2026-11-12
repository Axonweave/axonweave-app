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
AttemptStatus = Literal["in_progress", "submitted", "abandoned"]
EvaluationStatus = Literal["not_required", "pending", "completed", "failed"]
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
    status: AttemptStatus
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
    evaluation_status: EvaluationStatus = "not_required"
    time_taken_seconds: int | None = None


class AttemptResponse(BaseModel):
    success: bool = True
    data: AttemptOut


class AttemptSummary(BaseModel):
    id: uuid.UUID
    status: AttemptStatus
    started_at: datetime
    submitted_at: datetime | None
    auto_submitted: bool
    score: float | None
    total_questions: int | None
    graded_questions: int | None
    percentage: float | None
    evaluation_status: EvaluationStatus = "not_required"
    time_taken_seconds: int | None = None


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
    # A client-chosen key so a retried submit is recognised (unique per user, D-109).
    idempotency_key: str | None = Field(
        default=None, min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$"
    )


class EvaluationOut(BaseModel):
    """What the AI grader wrote for one written answer. It never contains the reference answer."""

    explanation: str
    covered_points: list[str]
    missing_points: list[str]
    ai_assisted: bool = True


class ResultQuestionOut(BaseModel):
    """The only schema that carries the answer key; reachable only for a submitted attempt."""

    id: uuid.UUID
    question: str
    question_type: QuestionTypeLiteral
    difficulty: Difficulty
    options: list[OptionOut]
    submitted_answer: list[str] | str | None
    answered: bool
    grading: Literal["auto", "ai", "self_assessment"]
    topic: str | None = None
    ai_assisted: bool = False
    evaluation_status: Literal["graded", "not_graded", "pending", "failed"] = "graded"
    evaluation: "EvaluationOut | None" = None
    is_correct: bool | None
    awarded_score: float
    # Option ids (choice), accepted answers (fill-in) or the model answer (written questions).
    correct_answers: list[str]
    rubric: list[str]
    explanation: str | None
    source_references: list[dict[str, Any]]


class TopicResultOut(BaseModel):
    topic: str | None
    questions: int
    correct: int
    percentage: float | None


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
    max_score: float = 0.0
    evaluation_status: EvaluationStatus = "not_required"
    pending_evaluations: int = 0
    ai_assisted_questions: int = 0
    topic_performance: list["TopicResultOut"] = Field(default_factory=list)
    suggested_topics: list[str] = Field(default_factory=list)
    suggested_topics_note: str = ""


class ResultResponse(BaseModel):
    success: bool = True
    data: ResultOut


class HistoryItem(AttemptSummary):
    """One attempt in the cross-quiz history."""

    quiz_id: uuid.UUID
    quiz_title: str
    subject_id: uuid.UUID | None
    chapter_id: uuid.UUID | None


class HistoryOut(BaseModel):
    items: list[HistoryItem]
    total: int
    limit: int
    offset: int


class HistoryResponse(BaseModel):
    success: bool = True
    data: HistoryOut


class CompareQuestionOut(BaseModel):
    question_id: uuid.UUID
    question: str
    topic: str | None
    first: Literal["correct", "incorrect", "partial", "unanswered", "pending", "not_graded"]
    second: Literal["correct", "incorrect", "partial", "unanswered", "pending", "not_graded"]
    movement: Literal["improved", "declined", "same"]


class CompareTopicOut(BaseModel):
    topic: str | None
    first_percentage: float | None
    second_percentage: float | None
    change: float | None


class CompareOut(BaseModel):
    first: AttemptSummary
    second: AttemptSummary
    score_change: float | None
    percentage_change: float | None
    time_change_seconds: int | None
    questions: list[CompareQuestionOut]
    topics: list[CompareTopicOut]
    note: str


class CompareResponse(BaseModel):
    success: bool = True
    data: CompareOut


class DeleteOut(BaseModel):
    deleted: bool = True


class DeleteResponse(BaseModel):
    success: bool = True
    data: DeleteOut
