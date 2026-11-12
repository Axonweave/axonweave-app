"""Revision API schemas (Phase 5 spec 5.2, 5.3).

Cards returned here are the user's own study content. Nothing in these schemas carries a quiz
answer key, a storage key or another user's data.
"""

import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Rating = Literal["again", "hard", "good", "easy"]
CardState = Literal["new", "learning", "review", "relearning"]
Bucket = Literal["due", "overdue", "new", "suspended", "all"]
SessionStatus = Literal["active", "completed", "abandoned"]
IdempotencyKey = Annotated[str, Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")]


class ScheduleOut(BaseModel):
    card_id: uuid.UUID
    state: CardState
    due_at: datetime
    stability: float | None
    difficulty: float | None
    elapsed_days: int
    scheduled_days: int
    repetitions: int
    lapses: int
    suspended: bool
    last_review_at: datetime | None
    # Model estimate of recall probability right now, or None for a card never reviewed.
    retrievability: float | None
    scheduler_version: str


class RevisionCardOut(BaseModel):
    id: uuid.UUID
    front: str
    back: str
    explanation: str | None
    card_type: str
    difficulty: str
    topic: str | None
    source_references: list[dict[str, Any]]
    study_material_id: uuid.UUID
    material_title: str
    subject_id: uuid.UUID | None
    chapter_id: uuid.UUID | None


class DueCardOut(BaseModel):
    card: RevisionCardOut
    schedule: ScheduleOut


class DueListOut(BaseModel):
    items: list[DueCardOut]
    total: int
    limit: int
    offset: int
    as_of: datetime
    day_start: datetime
    day_end: datetime
    timezone: str


class DueListResponse(BaseModel):
    success: bool = True
    data: DueListOut


class UpcomingDayOut(BaseModel):
    date: date
    count: int


class SubjectStatusOut(BaseModel):
    subject_id: uuid.UUID | None
    subject_name: str | None
    total: int
    due: int
    new: int


class RecentReviewOut(BaseModel):
    card_id: uuid.UUID
    rating: Rating
    reviewed_at: datetime


class SummaryOut(BaseModel):
    total_cards: int
    due_today: int
    overdue: int
    new: int
    learning: int
    review: int
    suspended: int
    reviewed_today: int
    # Share of today's planned reviews already done; None when nothing was planned.
    daily_completion: float | None
    new_cards_remaining_today: int
    upcoming: list[UpcomingDayOut]
    subjects: list[SubjectStatusOut]
    recent: list[RecentReviewOut]
    timezone: str
    desired_retention: float


class SummaryResponse(BaseModel):
    success: bool = True
    data: SummaryOut


class ScheduleResponse(BaseModel):
    success: bool = True
    data: ScheduleOut


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rating: Rating
    idempotency_key: IdempotencyKey
    response_time_ms: int | None = Field(default=None, ge=0, le=3_600_000)
    session_id: uuid.UUID | None = None


class ReviewEventOut(BaseModel):
    id: uuid.UUID
    card_id: uuid.UUID
    session_id: uuid.UUID | None
    rating: Rating
    reviewed_at: datetime
    elapsed_days: int
    scheduled_days: int
    response_time_ms: int | None
    previous_state: dict[str, Any]
    resulting_state: dict[str, Any]
    scheduler_version: str


class ReviewOut(BaseModel):
    review: ReviewEventOut
    schedule: ScheduleOut
    duplicate: bool = False


class ReviewResponse(BaseModel):
    success: bool = True
    data: ReviewOut


class ReviewHistoryOut(BaseModel):
    items: list[ReviewEventOut]
    total: int
    limit: int
    offset: int


class ReviewHistoryResponse(BaseModel):
    success: bool = True
    data: ReviewHistoryOut


class SessionStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject_id: uuid.UUID | None = None
    chapter_id: uuid.UUID | None = None
    limit: int | None = Field(default=None, ge=1, le=200)
    include_new: bool = True


class SessionSummaryOut(BaseModel):
    reviewed_cards: int
    total_cards: int
    rating_distribution: dict[str, int]
    duration_seconds: int | None
    average_response_ms: int | None
    next_due_at: datetime | None


class SessionOut(BaseModel):
    id: uuid.UUID
    status: SessionStatus
    started_at: datetime
    completed_at: datetime | None
    last_activity_at: datetime
    total_cards: int
    reviewed_cards: int
    duration_seconds: int | None
    subject_id: uuid.UUID | None
    chapter_id: uuid.UUID | None
    resumed: bool = False


class SessionCardOut(BaseModel):
    card: RevisionCardOut
    schedule: ScheduleOut
    reviewed: bool


class SessionDetailOut(SessionOut):
    cards: list[SessionCardOut]
    summary: SessionSummaryOut | None = None


class SessionResponse(BaseModel):
    success: bool = True
    data: SessionOut


class SessionDetailResponse(BaseModel):
    success: bool = True
    data: SessionDetailOut


class SessionListOut(BaseModel):
    items: list[SessionOut]
    total: int
    limit: int
    offset: int


class SessionListResponse(BaseModel):
    success: bool = True
    data: SessionListOut
