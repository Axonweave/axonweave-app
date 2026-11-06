"""AI API routes (spec 14). Every route needs an active session; services check ownership."""

import uuid
from typing import Literal

from fastapi import APIRouter, Query

from app.ai.orchestration.runtime import Runtime
from app.ai.orchestration.service import AiService
from app.core.dependencies import ActiveUser, DbSession
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
    ModelListResponse,
    ModelOut,
    ModelResponse,
    SendMessageData,
    SendMessageRequest,
    SendMessageResponse,
    UpdateConversationRequest,
    UsageOut,
)
from app.modules.ai.service import ConversationService, MessageService, ModelService

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


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=SendMessageResponse,
    status_code=201,
)
async def send_message(
    conversation_id: uuid.UUID,
    data: SendMessageRequest,
    current_user: ActiveUser,
    db: DbSession,
    runtime: Runtime,
) -> SendMessageResponse:
    result = await AiService(db, runtime).send_message(
        user=current_user,
        conversation_id=conversation_id,
        content=data.content,
        model_id=data.model_id,
        stream=data.stream,
    )
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
