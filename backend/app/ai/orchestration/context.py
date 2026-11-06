"""Context manager (D-47, D-48, spec section 10).

Builds the provider request from the system prompt, the conversation's history and the new message,
inside a token budget. Properties:

- the system prompt is returned separately and never mixed into user text;
- history is read for ONE conversation and ONE owner, nothing else is ever sent;
- only complete, successful turns are included (failed, cancelled, superseded and pending rows are
  ignored) and a turn is dropped whole, never cut in the middle;
- extra context (workspace, subject, chapter, documents) will plug in as additional `ContextSource`
  objects; Phase 2 ships only `ConversationHistory`.

Message text is never logged here: only counts.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from app.ai.errors import LLMContextTooLongError, LLMError
from app.ai.types import LLMMessage, Role
from app.core.logging import get_logger
from app.repositories.ai_message_repository import AiMessageRepository

logger = get_logger(__name__)

CHARS_PER_TOKEN = 3  # deliberately conservative (D-47)


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / CHARS_PER_TOKEN) if text else 0


@dataclass(frozen=True, slots=True)
class Turn:
    """One user message and its completed answer. Kept or dropped as a unit."""

    messages: tuple[LLMMessage, ...]

    @property
    def estimated_tokens(self) -> int:
        return sum(estimate_tokens(m.content) for m in self.messages)


@dataclass(frozen=True, slots=True)
class ContextRequest:
    conversation_id: uuid.UUID
    user_id: uuid.UUID
    new_message: str
    before_sequence: int  # the sequence number of the new user message


@dataclass(frozen=True, slots=True)
class ContextResult:
    system_prompt: str
    messages: list[LLMMessage]
    estimated: bool  # True when sizes are character estimates rather than provider counts
    dropped_messages: int
    input_tokens: int  # the figure that was compared with the budget


class ContextSource(Protocol):
    """A supplier of earlier turns. Order: oldest first."""

    async def turns(self, request: ContextRequest) -> list[Turn]: ...


class ConversationHistory:
    """The conversation's own earlier completed turns, limited to the last `limit` messages."""

    def __init__(self, repository: AiMessageRepository, *, limit: int) -> None:
        self._repo = repository
        self._limit = limit

    async def turns(self, request: ContextRequest) -> list[Turn]:
        rows = await self._repo.history(
            conversation_id=request.conversation_id,
            user_id=request.user_id,
            before_sequence=request.before_sequence,
        )
        rows = rows[-self._limit :]
        turns: list[Turn] = []
        pending_user: LLMMessage | None = None
        for row in rows:
            if row.role == "user":
                pending_user = LLMMessage(Role.user, row.content)  # a newer user row replaces it
            elif row.role == "assistant" and pending_user is not None:
                turns.append(Turn((pending_user, LLMMessage(Role.assistant, row.content))))
                pending_user = None
        return turns  # a trailing user row with no completed answer is not a complete turn


TokenCounter = Callable[[str, list[LLMMessage]], Awaitable[int | None]]
_MAX_RECOUNTS = 4


class ContextManager:
    def __init__(
        self,
        sources: Sequence[ContextSource],
        *,
        budget_tokens: int,
        counter: TokenCounter | None = None,
    ) -> None:
        self._sources = list(sources)
        self._budget = budget_tokens
        self._counter = counter

    async def build(self, request: ContextRequest, *, system_prompt: str) -> ContextResult:
        new_message = LLMMessage(Role.user, request.new_message)
        fixed = estimate_tokens(system_prompt) + estimate_tokens(request.new_message)
        if fixed > self._budget:
            raise LLMContextTooLongError()

        turns: list[Turn] = []
        for source in self._sources:
            turns.extend(await source.turns(request))

        kept: list[Turn] = []
        used = fixed
        for turn in reversed(turns):  # newest first; stop at the first turn that does not fit
            if used + turn.estimated_tokens > self._budget:
                break
            kept.append(turn)
            used += turn.estimated_tokens
        kept.reverse()

        estimated = True
        if self._counter is not None:
            for _ in range(_MAX_RECOUNTS + 1):
                messages = [m for t in kept for m in t.messages] + [new_message]
                try:
                    counted = await self._counter(system_prompt, messages)
                except LLMError:
                    counted = None  # fall back to the estimate rather than fail the request
                if counted is None:
                    break
                estimated = False
                used = counted
                if used <= self._budget:
                    break
                if not kept:
                    raise LLMContextTooLongError()
                kept.pop(0)  # still too big by the real count: drop the oldest turn and recount

        messages = [m for t in kept for m in t.messages] + [new_message]
        dropped = sum(len(t.messages) for t in turns) - sum(len(t.messages) for t in kept)
        logger.info(
            "ai_context_built",
            conversation_id=str(request.conversation_id),
            kept_messages=len(messages) - 1,
            dropped_messages=dropped,
            input_tokens=used,
            estimated=estimated,
        )
        return ContextResult(
            system_prompt=system_prompt,
            messages=messages,
            estimated=estimated,
            dropped_messages=dropped,
            input_tokens=used,
        )
