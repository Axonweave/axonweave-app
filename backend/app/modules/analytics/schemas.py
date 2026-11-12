"""Analytics API schemas (Phase 5 spec 3, 5.4). Every figure is derived from the caller's own
attempts, reviews and sessions. Fields that cannot be computed are null, never zero or invented."""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

TopicStatus = Literal["strong", "developing", "needs_revision", "not_enough_data"]
Trend = Literal["improving", "steady", "declining"]


class ThresholdsOut(BaseModel):
    strong_at: float
    needs_revision_below: float
    min_answers: int
    recent_attempts: int
    trend_delta: float


class OverviewOut(BaseModel):
    quizzes_attempted: int
    quiz_attempts: int
    average_quiz_percentage: float | None
    flashcards_reviewed: int
    distinct_cards_reviewed: int
    revision_sessions: int
    time_spent_seconds: int
    quiz_time_seconds: int
    revision_time_seconds: int
    current_streak_days: int
    longest_streak_days: int
    due_today: int
    overdue: int
    topics_needing_attention: int
    reviews_today: int
    quiz_attempts_today: int
    timezone: str
    note: str


class OverviewResponse(BaseModel):
    success: bool = True
    data: OverviewOut


class QuizPointOut(BaseModel):
    attempt_id: uuid.UUID
    quiz_id: uuid.UUID
    quiz_title: str
    submitted_at: datetime
    local_date: date
    percentage: float | None
    score: float | None
    max_score: float | None
    evaluation_status: str


class QuizPerformanceOut(BaseModel):
    points: list[QuizPointOut]
    attempts: int
    average_percentage: float | None
    note: str


class QuizPerformanceResponse(BaseModel):
    success: bool = True
    data: QuizPerformanceOut


class SubjectPerformanceItem(BaseModel):
    subject_id: uuid.UUID | None
    subject_name: str | None
    quiz_attempts: int
    average_quiz_percentage: float | None
    last_attempt_at: datetime | None
    reviews: int
    hard_or_again_share: float | None


class SubjectPerformanceOut(BaseModel):
    items: list[SubjectPerformanceItem]


class SubjectPerformanceResponse(BaseModel):
    success: bool = True
    data: SubjectPerformanceOut


class TopicOut(BaseModel):
    topic: str
    attempts: int
    answers: int
    correct: int
    accuracy: float | None
    recent_accuracy: float | None
    previous_accuracy: float | None
    trend: Trend | None
    status: TopicStatus
    status_label: str
    last_attempt_at: datetime | None


class TopicPerformanceOut(BaseModel):
    items: list[TopicOut]
    thresholds: ThresholdsOut
    note: str


class TopicPerformanceResponse(BaseModel):
    success: bool = True
    data: TopicPerformanceOut


class ActivityDayOut(BaseModel):
    date: date
    reviews: int
    again: int
    hard: int
    good: int
    easy: int
    sessions: int


class RevisionActivityOut(BaseModel):
    days: list[ActivityDayOut]
    total_reviews: int
    rating_distribution: dict[str, int]
    average_response_ms: int | None
    start_date: date
    end_date: date
    timezone: str


class RevisionActivityResponse(BaseModel):
    success: bool = True
    data: RevisionActivityOut


class CalendarDayOut(BaseModel):
    date: date
    quiz_attempts: int
    revision_sessions: int
    reviews: int
    activities: int


class StreakOut(BaseModel):
    current_streak_days: int
    longest_streak_days: int
    last_active_date: date | None
    active_days_total: int
    message: str


class CalendarOut(BaseModel):
    days: list[CalendarDayOut]
    streak: StreakOut
    start_date: date
    end_date: date
    timezone: str


class CalendarResponse(BaseModel):
    success: bool = True
    data: CalendarOut


class DayQuizOut(BaseModel):
    attempt_id: uuid.UUID
    quiz_id: uuid.UUID
    quiz_title: str
    submitted_at: datetime
    percentage: float | None
    time_taken_seconds: int | None


class DaySessionOut(BaseModel):
    session_id: uuid.UUID
    completed_at: datetime
    reviewed_cards: int
    total_cards: int
    duration_seconds: int | None


class DayDetailOut(BaseModel):
    date: date
    quizzes: list[DayQuizOut]
    sessions: list[DaySessionOut]
    reviews: int
    rating_distribution: dict[str, int]
    timezone: str


class DayDetailResponse(BaseModel):
    success: bool = True
    data: DayDetailOut


class StreakResponse(BaseModel):
    success: bool = True
    data: StreakOut
