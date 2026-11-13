"""Analytics routes (Phase 5 spec 5.4). Read-only; every figure is scoped to the caller. Dates are
the caller's local days (`YYYY-MM-DD`). A foreign subject or chapter id simply matches nothing."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.config import Settings, get_settings
from app.core.dependencies import ActiveUser, DbSession
from app.modules.analytics.schemas import (
    CalendarResponse,
    DayDetailResponse,
    OverviewResponse,
    QuizPerformanceResponse,
    RevisionActivityResponse,
    StreakResponse,
    SubjectPerformanceResponse,
    ThresholdsOut,
    TopicOut,
    TopicPerformanceOut,
    TopicPerformanceResponse,
)
from app.modules.analytics.service import (
    STATUS_LABELS,
    TOPIC_NOTE,
    AnalyticsService,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])
AppSettings = Annotated[Settings, Depends(get_settings)]
SubjectId = Annotated[uuid.UUID | None, Query()]
ChapterId = Annotated[uuid.UUID | None, Query()]
Start = Annotated[date | None, Query()]
End = Annotated[date | None, Query()]


@router.get("/overview", response_model=OverviewResponse)
async def overview(
    user: ActiveUser,
    db: DbSession,
    settings: AppSettings,
    subject_id: SubjectId = None,
    chapter_id: ChapterId = None,
    start_date: Start = None,
    end_date: End = None,
) -> OverviewResponse:
    data = await AnalyticsService(db, settings).overview(
        user, subject_id=subject_id, chapter_id=chapter_id, start=start_date, end=end_date
    )
    await db.commit()
    return OverviewResponse.model_validate({"data": data})


@router.get("/quiz-performance", response_model=QuizPerformanceResponse)
async def quiz_performance(
    user: ActiveUser,
    db: DbSession,
    settings: AppSettings,
    subject_id: SubjectId = None,
    chapter_id: ChapterId = None,
    start_date: Start = None,
    end_date: End = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> QuizPerformanceResponse:
    data = await AnalyticsService(db, settings).quiz_performance(
        user,
        subject_id=subject_id,
        chapter_id=chapter_id,
        start=start_date,
        end=end_date,
        limit=limit,
    )
    await db.commit()
    return QuizPerformanceResponse.model_validate({"data": data})


@router.get("/subject-performance", response_model=SubjectPerformanceResponse)
async def subject_performance(
    user: ActiveUser,
    db: DbSession,
    settings: AppSettings,
    subject_id: SubjectId = None,
    chapter_id: ChapterId = None,
    start_date: Start = None,
    end_date: End = None,
) -> SubjectPerformanceResponse:
    items = await AnalyticsService(db, settings).subject_performance(
        user, subject_id=subject_id, chapter_id=chapter_id, start=start_date, end=end_date
    )
    await db.commit()
    return SubjectPerformanceResponse.model_validate({"data": {"items": items}})


@router.get("/topic-performance", response_model=TopicPerformanceResponse)
async def topic_performance(
    user: ActiveUser,
    db: DbSession,
    settings: AppSettings,
    subject_id: SubjectId = None,
    chapter_id: ChapterId = None,
    start_date: Start = None,
    end_date: End = None,
) -> TopicPerformanceResponse:
    service = AnalyticsService(db, settings)
    stats = await service.topic_performance(
        user, subject_id=subject_id, chapter_id=chapter_id, start=start_date, end=end_date
    )
    await db.commit()
    t = service.thresholds
    return TopicPerformanceResponse(
        data=TopicPerformanceOut(
            items=[
                TopicOut(
                    topic=s.topic,
                    attempts=s.attempts,
                    answers=s.answers,
                    correct=s.correct,
                    accuracy=s.accuracy,
                    recent_accuracy=s.recent_accuracy,
                    previous_accuracy=s.previous_accuracy,
                    trend=s.trend,  # type: ignore[arg-type]
                    status=s.status,  # type: ignore[arg-type]
                    status_label=STATUS_LABELS[s.status],
                    last_attempt_at=s.last_attempt_at,
                )
                for s in stats
            ],
            thresholds=ThresholdsOut(
                strong_at=t.strong_at,
                needs_revision_below=t.needs_revision_below,
                min_answers=t.min_answers,
                recent_attempts=t.recent_attempts,
                trend_delta=t.trend_delta,
            ),
            note=TOPIC_NOTE,
        )
    )


@router.get("/revision-activity", response_model=RevisionActivityResponse)
async def revision_activity(
    user: ActiveUser,
    db: DbSession,
    settings: AppSettings,
    subject_id: SubjectId = None,
    chapter_id: ChapterId = None,
    start_date: Start = None,
    end_date: End = None,
) -> RevisionActivityResponse:
    data = await AnalyticsService(db, settings).revision_activity(
        user, subject_id=subject_id, chapter_id=chapter_id, start=start_date, end=end_date
    )
    await db.commit()
    return RevisionActivityResponse.model_validate({"data": data})


@router.get("/study-calendar", response_model=CalendarResponse)
async def study_calendar(
    user: ActiveUser,
    db: DbSession,
    settings: AppSettings,
    subject_id: SubjectId = None,
    chapter_id: ChapterId = None,
    start_date: Start = None,
    end_date: End = None,
) -> CalendarResponse:
    data = await AnalyticsService(db, settings).calendar(
        user, subject_id=subject_id, chapter_id=chapter_id, start=start_date, end=end_date
    )
    await db.commit()
    return CalendarResponse.model_validate({"data": data})


@router.get("/study-calendar/{day}", response_model=DayDetailResponse)
async def study_calendar_day(
    day: date, user: ActiveUser, db: DbSession, settings: AppSettings
) -> DayDetailResponse:
    data = await AnalyticsService(db, settings).day_detail(user, day)
    await db.commit()
    return DayDetailResponse.model_validate({"data": data})


@router.get("/streaks", response_model=StreakResponse)
async def streaks(user: ActiveUser, db: DbSession, settings: AppSettings) -> StreakResponse:
    data = await AnalyticsService(db, settings).streaks(user)
    await db.commit()
    return StreakResponse.model_validate({"data": data})
