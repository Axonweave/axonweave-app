"""Doubt popup helpers: the user turn is built here, with every piece of text marked as data.

Nothing here logs text.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.ai.rag import build_user_turn, escape_markup
from app.ai.types import LLMMessage, Role
from app.repositories.retrieval_repository import ChunkHit

QUICK_ACTIONS: dict[str, str] = {
    "simpler": "Explain the selected text in simpler words, as if to a beginner.",
    "analogy": "Explain the selected text with a clear everyday analogy.",
    "example": "Explain the selected text with a concrete worked example.",
    "step_by_step": "Explain the selected text step by step.",
}
HISTORY_TURNS = 12


def request_text(question: str | None, quick_action: str | None) -> str | None:
    """The student's request, or None when neither a question nor a quick action was given."""
    if question and question.strip():
        return question.strip()
    if quick_action in QUICK_ACTIONS:
        return QUICK_ACTIONS[quick_action]
    return None


def retrieval_query(selected_text: str, request: str) -> str:
    return f"{selected_text.strip()} {request}"[:1000]


def build_messages(
    *,
    selected_text: str,
    full_answer: str,
    request: str,
    history: Sequence[tuple[str, str]],
    sources: Sequence[ChunkHit],
) -> list[LLMMessage]:
    """Earlier popup turns first (alternating roles, oldest first), then the new turn, which carries
    the selected text, the full answer and the request."""
    turns = list(history)[-HISTORY_TURNS:]
    while turns and turns[0][0] != "user":
        turns.pop(0)
    clean: list[LLMMessage] = []
    for role, content in turns:
        if clean and clean[-1].role == role:
            continue  # keep strict alternation; a malformed history never breaks the request
        clean.append(
            LLMMessage(role=Role.user if role == "user" else Role.assistant, content=content)
        )
    if clean and clean[-1].role == Role.user:
        clean.pop()

    context = (
        f"SELECTED TEXT\n<<<SELECTED>>>\n{escape_markup(selected_text.strip())}\n<<<END SELECTED>>>"
        f"\n\nFULL ANSWER\n<<<ANSWER>>>\n{escape_markup(full_answer)}\n<<<END ANSWER>>>"
    )
    new_turn = f"{context}\n\nSTUDENT REQUEST\n{request}"
    if sources:
        new_turn = build_user_turn(new_turn, sources)
    return [*clean, LLMMessage(role=Role.user, content=new_turn)]
