"""Revision routes (Phase 5 spec 5.2, 5.3). All need an active session; ownership is checked in the
service and a foreign card or session id is a 404. Card-level routes live next to the existing card
routes under `/study/flashcards/cards/...`; list and session routes are under `/revision`."""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response

from app.core.config import Settings, get_settings
from app.core.dependencies import ActiveUser, DbSession
from app.models.revision import FlashcardReview, FlashcardScheduling, RevisionSession
from app.modules.revision.schemas import (
    Bucket,
    DueCardOut,
    DueListOut,
    DueListResponse,
    ReviewEventOut,
    ReviewHistoryOut,
    ReviewHistoryResponse,
    ReviewOut,
    ReviewRequest,
    ReviewResponse,
    RevisionCardOut,
    ScheduleOut,
    ScheduleResponse,
    SessionCardOut,
    SessionDetailOut,
    SessionDetailResponse,
    SessionListOut,
    SessionListResponse,
    SessionOut,
    SessionResponse,
    SessionStartRequest,
    SessionSummaryOut,
    SummaryOut,
    SummaryResponse,
)
from app.modules.revision.service import RevisionService, material_of
from app.repositories.revision_repository import Row

router = APIRouter(prefix="/revision", tags=["revision"])
card_router = APIRouter(prefix="/study/flashcards/cards", tags=["revision"])
AppSettings = Annotated[Settings, Depends(get_settings)]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0, le=100_000)]


def _schedule(
    service: RevisionService, sched: FlashcardScheduling, now: datetime | None = None
) -> ScheduleOut:
    return ScheduleOut(
        card_id=sched.flashcard_id,
        state=sched.state,  # type: ignore[arg-type]
        due_at=sched.due_at,
        stability=sched.stability,
        difficulty=sched.difficulty,
        elapsed_days=sched.elapsed_days,
        scheduled_days=sched.scheduled_days,
        repetitions=sched.repetitions,
        lapses=sched.lapses,
        suspended=sched.suspended,
        last_review_at=sched.last_review_at,
        retrievability=service.retrievability(sched, now or datetime.now(UTC)),
        scheduler_version=sched.scheduler_version,
    )


def _card(row: Row) -> RevisionCardOut:
    card, _, material = row
    return RevisionCardOut(
        id=card.id,
        front=card.front,
        back=card.back,
        explanation=card.explanation,
        card_type=card.card_type,
        difficulty=card.difficulty,
        topic=card.topic,
        source_references=list(card.source_references),
        study_material_id=material.id,
        material_title=material.title,
        subject_id=material_of(row).subject_id,
        chapter_id=material_of(row).chapter_id,
    )


def _event(e: FlashcardReview) -> ReviewEventOut:
    return ReviewEventOut(
        id=e.id,
        card_id=e.flashcard_id,
        session_id=e.session_id,
        rating=e.rating,  # type: ignore[arg-type]
        reviewed_at=e.reviewed_at,
        elapsed_days=e.elapsed_days,
        scheduled_days=e.scheduled_days,
        response_time_ms=e.response_time_ms,
        previous_state=e.previous_state,
        resulting_state=e.resulting_state,
        scheduler_version=e.scheduler_version,
    )


def _session(s: RevisionSession, *, resumed: bool = False) -> SessionOut:
    return SessionOut(
        id=s.id,
        status=s.status,  # type: ignore[arg-type]
        started_at=s.started_at,
        completed_at=s.completed_at,
        last_activity_at=s.last_activity_at,
        total_cards=s.total_cards,
        reviewed_cards=s.reviewed_cards,
        duration_seconds=s.duration_seconds,
        subject_id=s.subject_id,
        chapter_id=s.chapter_id,
        resumed=resumed,
    )


def _service(db: DbSession, settings: AppSettings) -> RevisionService:
    return RevisionService(db, settings)


async def _bucket_list(
    bucket: Bucket,
    user: ActiveUser,
    db: DbSession,
    settings: AppSettings,
    subject_id: uuid.UUID | None,
    chapter_id: uuid.UUID | None,
    limit: int,
    offset: int,
) -> DueListResponse:
    service = _service(db, settings)
    rows, total, now, start, end, zone = await service.list_cards(
        user,
        bucket=bucket,
        subject_id=subject_id,
        chapter_id=chapter_id,
        limit=limit,
        offset=offset,
    )
    return DueListResponse(
        data=DueListOut(
            items=[DueCardOut(card=_card(r), schedule=_schedule(service, r[1], now)) for r in rows],
            total=total,
            limit=limit,
            offset=offset,
            as_of=now,
            day_start=start,
            day_end=end,
            timezone=zone,
        )
    )


@router.get("/due", response_model=DueListResponse)
async def due_cards(
    current_user: ActiveUser,
    db: DbSession,
    settings: AppSettings,
    subject_id: Annotated[uuid.UUID | None, Query()] = None,
    chapter_id: Annotated[uuid.UUID | None, Query()] = None,
    limit: Limit = 20,
    offset: Offset = 0,
) -> DueListResponse:
    """Cards due by the end of the user's local day (overdue ones included), oldest due first."""
    return await _bucket_list(
        "due", current_user, db, settings, subject_id, chapter_id, limit, offset
    )


@router.get("/overdue", response_model=DueListResponse)
async def overdue_cards(
    current_user: ActiveUser,
    db: DbSession,
    settings: AppSettings,
    subject_id: Annotated[uuid.UUID | None, Query()] = None,
    chapter_id: Annotated[uuid.UUID | None, Query()] = None,
    limit: Limit = 20,
    offset: Offset = 0,
) -> DueListResponse:
    return await _bucket_list(
        "overdue", current_user, db, settings, subject_id, chapter_id, limit, offset
    )


@router.get("/new", response_model=DueListResponse)
async def new_cards(
    current_user: ActiveUser,
    db: DbSession,
    settings: AppSettings,
    subject_id: Annotated[uuid.UUID | None, Query()] = None,
    chapter_id: Annotated[uuid.UUID | None, Query()] = None,
    limit: Limit = 20,
    offset: Offset = 0,
) -> DueListResponse:
    return await _bucket_list(
        "new", current_user, db, settings, subject_id, chapter_id, limit, offset
    )


@router.get("/cards", response_model=DueListResponse)
async def filtered_cards(
    current_user: ActiveUser,
    db: DbSession,
    settings: AppSettings,
    bucket: Annotated[Bucket, Query()] = "all",
    subject_id: Annotated[uuid.UUID | None, Query()] = None,
    chapter_id: Annotated[uuid.UUID | None, Query()] = None,
    limit: Limit = 20,
    offset: Offset = 0,
) -> DueListResponse:
    """Any bucket (due, overdue, new, suspended, all) with the subject and chapter filters."""
    return await _bucket_list(
        bucket, current_user, db, settings, subject_id, chapter_id, limit, offset
    )


@router.get("/summary", response_model=SummaryResponse)
async def summary(
    current_user: ActiveUser,
    db: DbSession,
    settings: AppSettings,
    subject_id: Annotated[uuid.UUID | None, Query()] = None,
    chapter_id: Annotated[uuid.UUID | None, Query()] = None,
) -> SummaryResponse:
    data = await _service(db, settings).summary(
        current_user, subject_id=subject_id, chapter_id=chapter_id
    )
    return SummaryResponse(data=SummaryOut(**data))


# sessions ────────────────────────────────────────────────────────────────────


@router.post("/sessions", response_model=SessionResponse, status_code=201)
async def start_session(
    body: SessionStartRequest,
    response: Response,
    current_user: ActiveUser,
    db: DbSession,
    settings: AppSettings,
) -> SessionResponse:
    """Starts a session over the due cards, or returns the active one (200) so a refresh
    resumes it. 409 NOTHING_DUE when there is nothing to revise."""
    session, resumed = await _service(db, settings).start_session(
        current_user,
        subject_id=body.subject_id,
        chapter_id=body.chapter_id,
        limit=body.limit,
        include_new=body.include_new,
    )
    if resumed:
        response.status_code = 200
    return SessionResponse(data=_session(session, resumed=resumed))


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(
    current_user: ActiveUser,
    db: DbSession,
    settings: AppSettings,
    status: Annotated[Literal["active", "completed", "abandoned"] | None, Query()] = None,
    limit: Limit = 20,
    offset: Offset = 0,
) -> SessionListResponse:
    rows, total = await _service(db, settings).list_sessions(current_user, status, limit, offset)
    return SessionListResponse(
        data=SessionListOut(
            items=[_session(s) for s in rows], total=total, limit=limit, offset=offset
        )
    )


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session(
    session_id: uuid.UUID, current_user: ActiveUser, db: DbSession, settings: AppSettings
) -> SessionDetailResponse:
    service = _service(db, settings)
    session, items, summary_data = await service.get_session(current_user, session_id)
    now = datetime.now(UTC)
    base = _session(session).model_dump()
    return SessionDetailResponse(
        data=SessionDetailOut(
            **base,
            cards=[
                SessionCardOut(
                    card=_card(row), schedule=_schedule(service, row[1], now), reviewed=reviewed
                )
                for row, reviewed in items
            ],
            summary=SessionSummaryOut(**summary_data) if summary_data is not None else None,
        )
    )


@router.post("/sessions/{session_id}/complete", response_model=SessionResponse)
async def complete_session(
    session_id: uuid.UUID, current_user: ActiveUser, db: DbSession, settings: AppSettings
) -> SessionResponse:
    session = await _service(db, settings).complete_session(current_user, session_id)
    return SessionResponse(data=_session(session))


@router.post("/sessions/{session_id}/abandon", response_model=SessionResponse)
async def abandon_session(
    session_id: uuid.UUID, current_user: ActiveUser, db: DbSession, settings: AppSettings
) -> SessionResponse:
    session = await _service(db, settings).abandon_session(current_user, session_id)
    return SessionResponse(data=_session(session))


# one card ────────────────────────────────────────────────────────────────────


@card_router.get("/{card_id}/schedule", response_model=ScheduleResponse)
async def card_schedule(
    card_id: uuid.UUID, current_user: ActiveUser, db: DbSession, settings: AppSettings
) -> ScheduleResponse:
    service = _service(db, settings)
    return ScheduleResponse(data=_schedule(service, await service.schedule(current_user, card_id)))


@card_router.post("/{card_id}/review", response_model=ReviewResponse)
async def review_card(
    card_id: uuid.UUID,
    body: ReviewRequest,
    current_user: ActiveUser,
    db: DbSession,
    settings: AppSettings,
) -> ReviewResponse:
    """Idempotent on `idempotency_key`: a retry returns the stored event with duplicate=true."""
    service = _service(db, settings)
    event, sched, duplicate = await service.review(
        current_user,
        card_id,
        rating=body.rating,
        idempotency_key=body.idempotency_key,
        response_time_ms=body.response_time_ms,
        session_id=body.session_id,
    )
    return ReviewResponse(
        data=ReviewOut(
            review=_event(event), schedule=_schedule(service, sched), duplicate=duplicate
        )
    )


@card_router.patch("/{card_id}/suspend", response_model=ScheduleResponse)
async def suspend_card(
    card_id: uuid.UUID, current_user: ActiveUser, db: DbSession, settings: AppSettings
) -> ScheduleResponse:
    service = _service(db, settings)
    sched = await service.set_suspended(current_user, card_id, True)
    return ScheduleResponse(data=_schedule(service, sched))


@card_router.patch("/{card_id}/unsuspend", response_model=ScheduleResponse)
async def unsuspend_card(
    card_id: uuid.UUID, current_user: ActiveUser, db: DbSession, settings: AppSettings
) -> ScheduleResponse:
    service = _service(db, settings)
    sched = await service.set_suspended(current_user, card_id, False)
    return ScheduleResponse(data=_schedule(service, sched))


@card_router.get("/{card_id}/review-history", response_model=ReviewHistoryResponse)
async def review_history(
    card_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
    settings: AppSettings,
    limit: Limit = 20,
    offset: Offset = 0,
) -> ReviewHistoryResponse:
    rows, total = await _service(db, settings).history(current_user, card_id, limit, offset)
    return ReviewHistoryResponse(
        data=ReviewHistoryOut(
            items=[_event(e) for e in rows], total=total, limit=limit, offset=offset
        )
    )
