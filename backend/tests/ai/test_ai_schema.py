"""Database-level guarantees for the AI tables (D-61): the constraints live on the models, so they
exist in the test schema too, and each one is proven by trying to violate it."""

from typing import Any

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.model_registry import build_registry
from app.ai.prompts.registry import PROMPTS
from app.ai.sync import PromptImmutableError, sync_models, sync_prompts
from app.models.ai_usage_record import AiUsageRecord
from app.models.conversation import Conversation
from app.models.llm_provider import LLMModel, LLMProvider
from app.models.message import Message, MessageFeedback
from app.models.prompt_template import PromptTemplate
from tests.ai.test_provider_layer import make_settings
from tests.conftest import _make_user


async def _catalog(db: AsyncSession) -> tuple[LLMProvider, LLMModel]:
    provider = LLMProvider(name="fake", display_name="Fake")
    db.add(provider)
    await db.flush()
    model = LLMModel(
        provider_id=provider.id,
        model_key="m-one",
        provider_model_id="one",
        display_name="One",
        capabilities={},
    )
    db.add(model)
    await db.flush()
    return provider, model


async def _conversation(db: AsyncSession, user_id: Any) -> Conversation:
    conv = Conversation(user_id=user_id)
    db.add(conv)
    await db.flush()
    return conv


def _message(conv: Conversation, seq: int, **over: Any) -> Message:
    fields: dict[str, Any] = {
        "conversation_id": conv.id,
        "user_id": conv.user_id,
        "role": "user",
        "status": "completed",
        "sequence_number": seq,
        "content": "hi",
    }
    return Message(**{**fields, **over})


async def _violates(db: AsyncSession, *rows: Any) -> None:
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            db.add_all(rows)
            await db.flush()


async def test_message_cannot_point_at_another_users_conversation(db_session: AsyncSession) -> None:
    a = await _make_user(db_session, email="a@example.com")
    b = await _make_user(db_session, email="b@example.com")
    conv = await _conversation(db_session, a.id)
    await _violates(db_session, _message(conv, 1, user_id=b.id))


async def test_feedback_cannot_target_another_users_message(db_session: AsyncSession) -> None:
    a = await _make_user(db_session, email="a@example.com")
    b = await _make_user(db_session, email="b@example.com")
    conv = await _conversation(db_session, a.id)
    msg = _message(conv, 1, role="assistant")
    db_session.add(msg)
    await db_session.flush()
    await _violates(db_session, MessageFeedback(message_id=msg.id, user_id=b.id, rating="positive"))
    db_session.add(MessageFeedback(message_id=msg.id, user_id=a.id, rating="positive"))
    await db_session.flush()
    await _violates(
        db_session, MessageFeedback(message_id=msg.id, user_id=a.id, rating="negative")
    )  # one rating per user per message


async def test_only_one_active_generation_per_conversation(db_session: AsyncSession) -> None:
    user = await _make_user(db_session, email="a@example.com")
    conv = await _conversation(db_session, user.id)
    db_session.add(_message(conv, 1, role="assistant", status="streaming"))
    await db_session.flush()
    await _violates(db_session, _message(conv, 2, role="assistant", status="pending"))
    # Finished and user messages never conflict with the in-flight one.
    db_session.add_all([_message(conv, 3, role="assistant", status="completed"), _message(conv, 4)])
    await db_session.flush()


async def test_sequence_numbers_are_unique_per_conversation(db_session: AsyncSession) -> None:
    user = await _make_user(db_session, email="a@example.com")
    conv = await _conversation(db_session, user.id)
    db_session.add(_message(conv, 1))
    await db_session.flush()
    await _violates(db_session, _message(conv, 1))


@pytest.mark.parametrize(
    "over",
    [{"role": "system"}, {"status": "weird"}, {"sequence_number": 0}, {"usage_source": "guess"}],
)
async def test_message_check_constraints(db_session: AsyncSession, over: dict[str, Any]) -> None:
    user = await _make_user(db_session, email="a@example.com")
    conv = await _conversation(db_session, user.id)
    await _violates(db_session, _message(conv, 1, **over))


async def test_single_default_model_and_single_active_prompt(db_session: AsyncSession) -> None:
    provider, model = await _catalog(db_session)
    model.is_default = True
    await db_session.flush()
    await _violates(
        db_session,
        LLMModel(
            provider_id=provider.id,
            model_key="m-two",
            provider_model_id="two",
            display_name="Two",
            is_default=True,
            capabilities={},
        ),
    )
    db_session.add(
        PromptTemplate(
            prompt_key="k", version=1, content="a", content_sha256="0" * 64, is_active=True
        )
    )
    await db_session.flush()
    await _violates(
        db_session,
        PromptTemplate(
            prompt_key="k", version=2, content="b", content_sha256="1" * 64, is_active=True
        ),
    )


async def _usage(
    db: AsyncSession,
    user_id: Any,
    conv: Conversation | None,
    msg: Message | None,
    provider: LLMProvider,
    model: LLMModel,
) -> AiUsageRecord:
    record = AiUsageRecord(
        user_id=user_id,
        conversation_id=conv.id if conv else None,
        message_id=msg.id if msg else None,
        provider_id=provider.id,
        model_id=model.id,
        input_tokens=10,
        output_tokens=None,  # unknown stays NULL
        request_status="success",
    )
    db.add(record)
    await db.flush()
    return record


async def test_usage_survives_conversation_delete_and_keeps_owner(db_session: AsyncSession) -> None:
    user = await _make_user(db_session, email="a@example.com")
    provider, model = await _catalog(db_session)
    conv = await _conversation(db_session, user.id)
    msg = _message(conv, 1, role="assistant")
    db_session.add(msg)
    await db_session.flush()
    record = await _usage(db_session, user.id, conv, msg, provider, model)
    record_id, user_id = record.id, user.id

    await db_session.execute(delete(Conversation).where(Conversation.id == conv.id))
    db_session.expire_all()

    kept = (
        await db_session.execute(select(AiUsageRecord).where(AiUsageRecord.id == record_id))
    ).scalar_one()
    assert kept.user_id == user_id  # owner column is NOT cleared
    assert kept.conversation_id is None
    assert kept.message_id is None  # the message cascaded away with its conversation
    assert kept.input_tokens == 10 and kept.output_tokens is None


async def test_usage_survives_message_delete_only_clearing_message(
    db_session: AsyncSession,
) -> None:
    user = await _make_user(db_session, email="a@example.com")
    provider, model = await _catalog(db_session)
    conv = await _conversation(db_session, user.id)
    msg = _message(conv, 1, role="assistant")
    db_session.add(msg)
    await db_session.flush()
    record = await _usage(db_session, user.id, conv, msg, provider, model)
    record_id, conv_id = record.id, conv.id

    await db_session.execute(delete(Message).where(Message.id == msg.id))
    db_session.expire_all()
    kept = (
        await db_session.execute(select(AiUsageRecord).where(AiUsageRecord.id == record_id))
    ).scalar_one()
    assert kept.conversation_id == conv_id and kept.message_id is None


async def test_usage_cannot_reference_another_users_conversation(
    db_session: AsyncSession,
) -> None:
    a = await _make_user(db_session, email="a@example.com")
    b = await _make_user(db_session, email="b@example.com")
    provider, model = await _catalog(db_session)
    conv = await _conversation(db_session, a.id)
    await _violates(
        db_session,
        AiUsageRecord(
            user_id=b.id,
            conversation_id=conv.id,
            provider_id=provider.id,
            model_id=model.id,
            request_status="success",
        ),
    )


async def test_deleting_a_user_removes_their_ai_data(db_session: AsyncSession) -> None:
    from app.models.user import User

    user = await _make_user(db_session, email="a@example.com")
    provider, model = await _catalog(db_session)
    conv = await _conversation(db_session, user.id)
    await _usage(db_session, user.id, conv, None, provider, model)
    await db_session.execute(delete(User).where(User.id == user.id))
    for table in ("conversations", "ai_usage_records"):
        count = (await db_session.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one()
        assert count == 0


async def test_model_with_usage_cannot_be_deleted(db_session: AsyncSession) -> None:
    user = await _make_user(db_session, email="a@example.com")
    provider, model = await _catalog(db_session)
    await _usage(db_session, user.id, None, None, provider, model)
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await db_session.execute(delete(LLMModel).where(LLMModel.id == model.id))


async def test_negative_tokens_rejected(db_session: AsyncSession) -> None:
    user = await _make_user(db_session, email="a@example.com")
    provider, model = await _catalog(db_session)
    await _violates(
        db_session,
        AiUsageRecord(
            user_id=user.id,
            provider_id=provider.id,
            model_id=model.id,
            input_tokens=-1,
            request_status="success",
        ),
    )


# ── startup sync ─────────────────────────────────────────────────────────────


async def test_sync_is_idempotent_and_marks_one_default(db_session: AsyncSession) -> None:
    registry = build_registry(make_settings(llm_provider="fake", llm_allowed_models="other"))
    for _ in range(2):
        await sync_prompts(db_session)
        await sync_models(db_session, registry)
    models = (await db_session.execute(select(LLMModel))).scalars().all()
    assert len(models) == 2
    assert [m.provider_model_id for m in models if m.is_default] == ["fake-model"]
    prompts = (await db_session.execute(select(PromptTemplate))).scalars().all()
    assert len(prompts) == len(PROMPTS)
    assert all(p.is_active for p in prompts)


async def test_sync_does_nothing_without_a_provider(db_session: AsyncSession) -> None:
    await sync_models(db_session, build_registry(make_settings()))
    assert (await db_session.execute(select(LLMModel))).first() is None


async def test_changed_prompt_text_for_a_released_version_is_refused(
    db_session: AsyncSession,
) -> None:
    await sync_prompts(db_session)
    await db_session.execute(text("UPDATE prompt_templates SET content_sha256 = repeat('0', 64)"))
    with pytest.raises(PromptImmutableError):
        await sync_prompts(db_session)


async def test_removed_model_is_disabled_not_deleted(db_session: AsyncSession) -> None:
    await sync_models(
        db_session, build_registry(make_settings(llm_provider="fake", llm_allowed_models="extra"))
    )
    await sync_models(db_session, build_registry(make_settings(llm_provider="fake")))
    rows = {
        m.provider_model_id: m.is_enabled
        for m in (await db_session.execute(select(LLMModel))).scalars().all()
    }
    assert rows == {"fake-model": True, "extra": False}


# ── grants ───────────────────────────────────────────────────────────────────

_AI_TABLES = [
    "llm_providers",
    "llm_models",
    "llm_model_prices",
    "prompt_templates",
    "conversations",
    "messages",
    "message_feedback",
    "ai_usage_records",
]


async def test_app_role_can_use_ai_tables(db_session: AsyncSession) -> None:
    exists = (
        await db_session.execute(text("SELECT 1 FROM pg_roles WHERE rolname = 'axonweave_app'"))
    ).first()
    if exists is None:
        pytest.skip("axonweave_app role not present in this database (no init-db.sql)")
    for table in _AI_TABLES:
        granted = (
            await db_session.execute(
                text(
                    "SELECT has_table_privilege('axonweave_app', :t, 'SELECT,INSERT,UPDATE,DELETE')"
                ),
                {"t": table},
            )
        ).scalar_one()
        assert granted, table
