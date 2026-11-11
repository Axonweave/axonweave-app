"""Read helpers for glossary and question bank materials (spec 9.3, 11.2): search, filter and
sort over the stored content. Ownership comes from the same material lookup as every other
material route (foreign or missing is a 404). The question bank view is the public one: it never
contains an answer key, explanation or rubric (the content stores none, D-94)."""

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.ai.orchestration.runtime import AiRuntime, Runtime
from app.core.dependencies import ActiveUser, DbSession
from app.core.rate_limit import get_rate_limiter
from app.modules.study.service import StudyGenerationService
from app.study.dispatch import GenerationDispatcher, get_generation_dispatcher
from app.study.errors import MaterialNotFoundError
from app.study.generators.glossary import search_terms

router = APIRouter(prefix="/study/materials", tags=["study"])

Dispatcher = Annotated[GenerationDispatcher, Depends(get_generation_dispatcher)]


class ListResponse(BaseModel):
    success: bool = True
    data: list[dict[str, Any]]
    total: int


async def _payload(
    db: DbSession,
    runtime: AiRuntime,
    dispatcher: GenerationDispatcher,
    user: ActiveUser,
    material_id: uuid.UUID,
    resource_type: str,
) -> dict[str, Any]:
    service = StudyGenerationService(db, runtime, dispatcher, get_rate_limiter())
    material = await service.get_material(user, material_id)
    if material.resource_type != resource_type:
        raise MaterialNotFoundError
    payload = material.content.get("payload")
    return payload if isinstance(payload, dict) else {}


@router.get("/{material_id}/glossary", response_model=ListResponse)
async def search_glossary(
    material_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
    runtime: Runtime,
    dispatcher: Dispatcher,
    q: Annotated[str | None, Query(max_length=100)] = None,
    topic: Annotated[str | None, Query(max_length=120)] = None,
    order: Literal["asc", "desc"] = "asc",
) -> ListResponse:
    payload = await _payload(db, runtime, dispatcher, current_user, material_id, "glossary")
    found = search_terms(list(payload.get("terms", [])), q, topic, order == "desc")
    return ListResponse(data=found, total=len(found))


@router.get("/{material_id}/questions", response_model=ListResponse)
async def filter_bank_questions(
    material_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
    runtime: Runtime,
    dispatcher: Dispatcher,
    q: Annotated[str | None, Query(max_length=100)] = None,
    topic: Annotated[str | None, Query(max_length=120)] = None,
    difficulty: Literal["easy", "medium", "hard"] | None = None,
    question_type: Annotated[str | None, Query(max_length=32, pattern=r"^[a-z_]+$")] = None,
) -> ListResponse:
    payload = await _payload(db, runtime, dispatcher, current_user, material_id, "question_bank")
    needle = (q or "").strip().casefold()
    found = [
        item
        for item in payload.get("questions", [])
        if (not topic or str(item.get("topic", "")).casefold() == topic.casefold())
        and (difficulty is None or item.get("difficulty") == difficulty)
        and (question_type is None or item.get("question_type") == question_type)
        and (not needle or needle in str(item.get("question", "")).casefold())
    ]
    return ListResponse(data=found, total=len(found))
