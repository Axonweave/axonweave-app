"""Flashcard routes (spec 19.3 plus reorder and regenerate-selected). All need an active session;
ownership is checked in the service and a foreign id is a 404."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.ai.orchestration.runtime import Runtime
from app.core.dependencies import ActiveUser, DbSession
from app.core.rate_limit import get_rate_limiter
from app.models.flashcard import Flashcard
from app.modules.study.flashcard_schemas import (
    AddCardRequest,
    EditCardRequest,
    FlashcardListResponse,
    FlashcardOut,
    FlashcardResponse,
    FlashcardSetOut,
    FlashcardSetResponse,
    RegenerateCardsRequest,
    ReorderRequest,
)
from app.modules.study.flashcard_service import FlashcardService
from app.modules.study.routes import _out
from app.modules.study.schemas import GenerationJobResponse
from app.modules.study.service import StudyGenerationService
from app.study.dispatch import GenerationDispatcher, get_generation_dispatcher

router = APIRouter(prefix="/study/flashcards", tags=["study-flashcards"])
Dispatcher = Annotated[GenerationDispatcher, Depends(get_generation_dispatcher)]


def _service(db: DbSession, runtime: Runtime, dispatcher: GenerationDispatcher) -> FlashcardService:
    gen = StudyGenerationService(db, runtime, dispatcher, get_rate_limiter())
    return FlashcardService(db, runtime.settings, gen)


def _cards(rows: list[Flashcard]) -> list[FlashcardOut]:
    return [FlashcardOut.model_validate(c) for c in rows]


@router.get("/{set_id}", response_model=FlashcardSetResponse)
async def get_set(
    set_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
    runtime: Runtime,
    dispatcher: Dispatcher,
) -> FlashcardSetResponse:
    card_set, material, cards = await _service(db, runtime, dispatcher).get(current_user, set_id)
    return FlashcardSetResponse(
        data=FlashcardSetOut(
            id=card_set.id,
            study_material_id=material.id,
            workspace_id=material.workspace_id,
            subject_id=material.subject_id,
            chapter_id=material.chapter_id,
            title=material.title,
            generation_settings=material.generation_settings,
            card_count=len(cards),
            cards=_cards(cards),
            created_at=card_set.created_at,
            updated_at=card_set.updated_at,
        )
    )


@router.post("/{set_id}/cards", response_model=FlashcardResponse, status_code=201)
async def add_card(
    set_id: uuid.UUID,
    body: AddCardRequest,
    current_user: ActiveUser,
    db: DbSession,
    runtime: Runtime,
    dispatcher: Dispatcher,
) -> FlashcardResponse:
    card = await _service(db, runtime, dispatcher).add_card(current_user, set_id, body.model_dump())
    return FlashcardResponse(data=FlashcardOut.model_validate(card))


@router.patch("/cards/{card_id}", response_model=FlashcardResponse)
async def edit_card(
    card_id: uuid.UUID,
    body: EditCardRequest,
    current_user: ActiveUser,
    db: DbSession,
    runtime: Runtime,
    dispatcher: Dispatcher,
) -> FlashcardResponse:
    card = await _service(db, runtime, dispatcher).edit_card(
        current_user, card_id, body.model_dump(exclude_unset=True)
    )
    return FlashcardResponse(data=FlashcardOut.model_validate(card))


@router.delete("/cards/{card_id}", status_code=204)
async def delete_card(
    card_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
    runtime: Runtime,
    dispatcher: Dispatcher,
) -> Response:
    await _service(db, runtime, dispatcher).delete_card(current_user, card_id)
    return Response(status_code=204)


@router.put("/{set_id}/order", response_model=FlashcardListResponse)
async def reorder_cards(
    set_id: uuid.UUID,
    body: ReorderRequest,
    current_user: ActiveUser,
    db: DbSession,
    runtime: Runtime,
    dispatcher: Dispatcher,
) -> FlashcardListResponse:
    rows = await _service(db, runtime, dispatcher).reorder(current_user, set_id, body.card_ids)
    return FlashcardListResponse(data=_cards(rows))


@router.post("/{set_id}/regenerate", response_model=GenerationJobResponse, status_code=202)
async def regenerate_cards(
    set_id: uuid.UUID,
    body: RegenerateCardsRequest,
    response: Response,
    current_user: ActiveUser,
    db: DbSession,
    runtime: Runtime,
    dispatcher: Dispatcher,
) -> GenerationJobResponse:
    """Starts a job whose result is a preview (GET /study/generations/{id}/preview); no card
    changes until POST /study/flashcards/{set_id}/regenerate/{job_id}/apply."""
    job, existing = await _service(db, runtime, dispatcher).regenerate(
        current_user, set_id, body.card_ids, body.settings
    )
    if existing:
        response.status_code = 200
    return GenerationJobResponse(data=_out(job, existing=existing))


@router.post("/{set_id}/regenerate/{job_id}/apply", response_model=FlashcardListResponse)
async def apply_regeneration(
    set_id: uuid.UUID,
    job_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
    runtime: Runtime,
    dispatcher: Dispatcher,
) -> FlashcardListResponse:
    rows = await _service(db, runtime, dispatcher).apply_regeneration(current_user, set_id, job_id)
    return FlashcardListResponse(data=_cards(rows))
