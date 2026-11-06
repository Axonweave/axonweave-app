"""AI API routes (spec 14). Every route needs an active session; services check ownership."""

import time
import uuid
from typing import Any, Literal

from fastapi import APIRouter, Query, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.orchestration.runtime import AiRuntime, Runtime, SessionFactory
from app.ai.orchestration.service import AiService, GenerationResult, Prepared
from app.ai.orchestration.streaming import SSE_HEADERS, StreamRunner
from app.core.dependencies import ActiveUser, DbSession
from app.models.user import User
from app.modules.ai.schemas import (
    CapabilitiesOut,
    CapabilitiesResponse,
    ConversationListResponse,
    ConversationOut,
    ConversationResponse,
    CreateConversationRequest,
    FeedbackOut,
    FeedbackRequest,
    FeedbackResponse,
    MessageListResponse,
    MessageOut,
    MessageResponse,
    ModelListResponse,
    ModelOut,
    ModelResponse,
    RegenerateRequest,
    SendMessageData,
    SendMessageRequest,
    SendMessageResponse,
    UpdateConversationRequest,
    UsageByModelOut,
    UsageByModelResponse,
    UsageListResponse,
    UsageOut,
    UsageRecordOut,
    UsageSummaryOut,
    UsageSummaryResponse,
)
from app.modules.ai.service import (
    ConversationService,
    MessageService,
    ModelService,
    UsageService,
)

router = APIRouter(prefix="/ai", tags=["ai"])

_MAX_LIMIT = 100


# ── conversations ────────────────────────────────────────────────────────────


@router.post("/conversations", response_model=ConversationResponse, status_code=201)
async def create_conversation(
    data: CreateConversationRequest, current_user: ActiveUser, db: DbSession, runtime: Runtime
) -> ConversationResponse:
    conv = await ConversationService(db, runtime).create(
        user=current_user, title=data.title, model_id=data.model_id
    )
    return ConversationResponse(data=ConversationOut.model_validate(conv))


@router.get("/conversations", response_model=ConversationListResponse)
async def list_conversations(
    current_user: ActiveUser,
    db: DbSession,
    runtime: Runtime,
    status: Literal["active", "archived"] | None = Query(default="active"),
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=30, ge=1, le=_MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> ConversationListResponse:
    rows, total = await ConversationService(db, runtime).list(
        user=current_user, status=status, q=q, limit=limit, offset=offset
    )
    return ConversationListResponse(
        data=[ConversationOut.model_validate(c) for c in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: uuid.UUID, current_user: ActiveUser, db: DbSession, runtime: Runtime
) -> ConversationResponse:
    conv = await ConversationService(db, runtime).get(
        user=current_user, conversation_id=conversation_id
    )
    return ConversationResponse(data=ConversationOut.model_validate(conv))


@router.patch("/conversations/{conversation_id}", response_model=ConversationResponse)
async def rename_conversation(
    conversation_id: uuid.UUID,
    data: UpdateConversationRequest,
    current_user: ActiveUser,
    db: DbSession,
    runtime: Runtime,
) -> ConversationResponse:
    conv = await ConversationService(db, runtime).rename(
        user=current_user, conversation_id=conversation_id, title=data.title
    )
    return ConversationResponse(data=ConversationOut.model_validate(conv))


@router.post("/conversations/{conversation_id}/archive", response_model=ConversationResponse)
async def archive_conversation(
    conversation_id: uuid.UUID, current_user: ActiveUser, db: DbSession, runtime: Runtime
) -> ConversationResponse:
    conv = await ConversationService(db, runtime).archive(
        user=current_user, conversation_id=conversation_id
    )
    return ConversationResponse(data=ConversationOut.model_validate(conv))


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: uuid.UUID, current_user: ActiveUser, db: DbSession, runtime: Runtime
) -> None:
    await ConversationService(db, runtime).delete(
        user=current_user, conversation_id=conversation_id
    )


# ── messages ─────────────────────────────────────────────────────────────────


@router.get("/conversations/{conversation_id}/messages", response_model=MessageListResponse)
async def list_messages(
    conversation_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
    limit: int = Query(default=100, ge=1, le=_MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> MessageListResponse:
    rows, total = await MessageService(db).list(
        user=current_user, conversation_id=conversation_id, limit=limit, offset=offset
    )
    return MessageListResponse(
        data=[MessageOut.model_validate(m) for m in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


_SSE_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {
        "description": (
            "Returned instead of the JSON envelope when `stream` is true: a server-sent event "
            "stream with the events message.started, message.delta, usage.updated, "
            "message.completed, message.failed and message.cancelled, plus `: ping` heartbeats."
        ),
        "content": {"text/event-stream": {"schema": {"type": "string"}}},
    }
}


def _result_response(result: GenerationResult) -> SendMessageResponse:
    usage = result.usage
    return SendMessageResponse(
        data=SendMessageData(
            conversation_id=result.conversation.id,
            user_message=MessageOut.model_validate(result.user_message),
            message=MessageOut.model_validate(result.assistant_message),
            usage=UsageOut(
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                reasoning_tokens=usage.reasoning_tokens,
                source=usage.source.value,
            ),
        )
    )


async def _stream(
    service: AiService,
    runtime: AiRuntime,
    factory: async_sessionmaker[AsyncSession],
    user: User,
    prepared: Prepared,
    started: float,
) -> StreamingResponse:
    """Everything that can fail with a normal HTTP error happens before this point and before the
    first event (ownership, validation, quotas, reserve, context). From here on, failures are
    reported as `message.failed` events."""
    context = await service.build_context_or_fail(user=user, prepared=prepared, started=started)
    runner = StreamRunner(runtime, factory)
    return StreamingResponse(
        runner.events(prepared, context, started),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=SendMessageResponse,
    status_code=201,
    responses=_SSE_RESPONSES,
)
async def send_message(
    conversation_id: uuid.UUID,
    data: SendMessageRequest,
    current_user: ActiveUser,
    db: DbSession,
    runtime: Runtime,
    factory: SessionFactory,
) -> Response:
    service = AiService(db, runtime)
    if data.stream:
        started = time.monotonic()
        prepared = await service.prepare(
            user=current_user,
            conversation_id=conversation_id,
            content=data.content,
            model_id=data.model_id,
        )
        return await _stream(service, runtime, factory, current_user, prepared, started)
    result = await service.send_message(
        user=current_user,
        conversation_id=conversation_id,
        content=data.content,
        model_id=data.model_id,
    )
    return JSONResponse(status_code=201, content=jsonable_encoder(_result_response(result)))


@router.post(
    "/conversations/{conversation_id}/messages/{message_id}/regenerate",
    response_model=SendMessageResponse,
    status_code=201,
    responses=_SSE_RESPONSES,
)
async def regenerate_message(
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    data: RegenerateRequest,
    current_user: ActiveUser,
    db: DbSession,
    runtime: Runtime,
    factory: SessionFactory,
) -> Response:
    service = AiService(db, runtime)
    if data.stream:
        started = time.monotonic()
        prepared = await service.prepare_regenerate(
            user=current_user,
            conversation_id=conversation_id,
            message_id=message_id,
            model_id=data.model_id,
        )
        return await _stream(service, runtime, factory, current_user, prepared, started)
    result = await service.regenerate(
        user=current_user,
        conversation_id=conversation_id,
        message_id=message_id,
        model_id=data.model_id,
    )
    return JSONResponse(status_code=201, content=jsonable_encoder(_result_response(result)))


@router.post(
    "/conversations/{conversation_id}/messages/{message_id}/cancel",
    response_model=MessageResponse,
)
async def cancel_generation(
    conversation_id: uuid.UUID, message_id: uuid.UUID, current_user: ActiveUser, db: DbSession
) -> MessageResponse:
    message = await MessageService(db).cancel(
        user=current_user, conversation_id=conversation_id, message_id=message_id
    )
    return MessageResponse(data=MessageOut.model_validate(message))


@router.post("/messages/{message_id}/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    message_id: uuid.UUID, data: FeedbackRequest, current_user: ActiveUser, db: DbSession
) -> FeedbackResponse:
    row = await MessageService(db).submit_feedback(
        user=current_user,
        message_id=message_id,
        rating=data.rating,
        text=data.feedback_text,
    )
    return FeedbackResponse(data=FeedbackOut.model_validate(row))


# ── usage ────────────────────────────────────────────────────────────────────

_MAX_WINDOW_DAYS = 90


@router.get("/usage", response_model=UsageListResponse)
async def list_usage(
    current_user: ActiveUser,
    db: DbSession,
    status: Literal["success", "failed", "cancelled"] | None = Query(default=None),
    days: int = Query(default=30, ge=1, le=_MAX_WINDOW_DAYS),
    limit: int = Query(default=50, ge=1, le=_MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> UsageListResponse:
    rows, total = await UsageService(db).list(
        user=current_user, status=status, days=days, limit=limit, offset=offset
    )
    return UsageListResponse(
        data=[UsageRecordOut.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/usage/summary", response_model=UsageSummaryResponse)
async def usage_summary(
    current_user: ActiveUser,
    db: DbSession,
    days: int = Query(default=30, ge=1, le=_MAX_WINDOW_DAYS),
) -> UsageSummaryResponse:
    data = await UsageService(db).summary(user=current_user, days=days)
    return UsageSummaryResponse(data=UsageSummaryOut.model_validate(data))


@router.get("/usage/by-model", response_model=UsageByModelResponse)
async def usage_by_model(
    current_user: ActiveUser,
    db: DbSession,
    days: int = Query(default=30, ge=1, le=_MAX_WINDOW_DAYS),
) -> UsageByModelResponse:
    rows = await UsageService(db).by_model(user=current_user, days=days)
    return UsageByModelResponse(days=days, data=[UsageByModelOut.model_validate(r) for r in rows])


# ── models ───────────────────────────────────────────────────────────────────


@router.get("/models", response_model=ModelListResponse)
async def list_models(current_user: ActiveUser, runtime: Runtime) -> ModelListResponse:
    return ModelListResponse(
        data=[ModelOut.model_validate(m) for m in ModelService(runtime).list()]
    )


@router.get("/models/default", response_model=ModelResponse)
async def default_model(current_user: ActiveUser, runtime: Runtime) -> ModelResponse:
    return ModelResponse(data=ModelOut.model_validate(ModelService(runtime).default()))


@router.get("/capabilities", response_model=CapabilitiesResponse)
async def capabilities(current_user: ActiveUser, runtime: Runtime) -> CapabilitiesResponse:
    return CapabilitiesResponse(
        data=CapabilitiesOut.model_validate(ModelService(runtime).capabilities())
    )
