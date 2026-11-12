"""Phase 5 M0 (D-102): quiz questions and flashcards carry a topic label from generation, the
prompts are version 2 (version 1 kept), and an empty or missing topic is stored as NULL."""

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompts.registry import PROMPTS, active_prompt
from app.models.flashcard import Flashcard
from app.models.quiz import QuizQuestion
from tests.conftest import _TestSessionLocal
from tests.retrieval.test_search import Actor
from tests.study.conftest import Harness
from tests.study.test_flashcards import GOOD_CARDS, make_deck
from tests.study.test_quiz import MC, TF, make_quiz


def test_prompts_are_version_2_and_version_1_is_kept_unchanged() -> None:
    for key in ("study_quiz", "study_flashcards"):
        versions = sorted(p.version for p in PROMPTS if p.prompt_key == key)
        assert versions == [1, 2]
        v1 = next(p for p in PROMPTS if p.prompt_key == key and p.version == 1)
        v2 = active_prompt(key)
        assert v2.version == 2
        assert v2.content.startswith(v1.content)  # version 1 text is a strict prefix: untouched
        assert '"topic"' in v2.content and '"topic"' not in v1.content


async def test_quiz_questions_store_the_topic(
    client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
) -> None:
    questions = [
        {**MC, "topic": "  Photosynthesis "},
        {**TF, "topic": ""},  # empty becomes NULL
    ]
    await make_quiz(client, study, alice, db_session, questions)
    async with _TestSessionLocal() as s:
        rows = (await s.execute(select(QuizQuestion))).scalars().all()
    topics = {r.question_type: r.topic for r in rows}
    assert topics == {"multiple_choice": "Photosynthesis", "true_false": None}


async def test_flashcards_store_the_topic(
    client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
) -> None:
    cards = [{**GOOD_CARDS[0], "topic": "Cell energy"}, *GOOD_CARDS[1:]]
    await make_deck(client, study, alice, db_session, cards)
    async with _TestSessionLocal() as s:
        rows = (
            (await s.execute(select(Flashcard).order_by(Flashcard.display_order))).scalars().all()
        )
    assert rows[0].topic == "Cell energy"
    assert all(r.topic is None for r in rows[1:])
