"""Create generated-style study materials for ONE existing user, for the Playwright tests.

The end-to-end stack runs on the FakeProvider, which cannot write structured study output, so the
browser tests need ready-made materials. This script builds them directly through the repositories:
no model call, no cost, generated fixtures only (D-76). It refuses to run unless APP_ENV is
`development` or `testing`, and it only touches the user named on the command line.

  docker compose exec -T backend python scripts/seed_study_e2e.py user@example.com

Prints one JSON object with the ids it created (never any key or secret).
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select  # noqa: E402

from app.core.config import AppEnv, get_settings  # noqa: E402
from app.database.connection import AsyncSessionLocal  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.workspace import Workspace  # noqa: E402
from app.repositories.flashcard_repository import FlashcardRepository  # noqa: E402
from app.repositories.quiz_repository import QuizRepository  # noqa: E402
from app.repositories.study_material_repository import StudyMaterialRepository  # noqa: E402

SOURCES: list[dict[str, Any]] = [{"rank": 1, "kind": "text"}]


def questions() -> list[dict[str, Any]]:
    return [
        {
            "question": "Which organelle produces most of the cell's ATP?",
            "question_type": "multiple_choice",
            "difficulty": "easy",
            "options": [
                {"id": "A", "text": "Mitochondrion"},
                {"id": "B", "text": "Ribosome"},
                {"id": "C", "text": "Golgi apparatus"},
            ],
            "correct_answers": ["A"],
            "rubric": [],
            "explanation": "E2E-EXPLANATION-ONE",
            "source_references": [],
        },
        {
            "question": "Photosynthesis takes place in chloroplasts.",
            "question_type": "true_false",
            "difficulty": "easy",
            "options": [{"id": "true", "text": "True"}, {"id": "false", "text": "False"}],
            "correct_answers": ["true"],
            "rubric": [],
            "explanation": "E2E-EXPLANATION-TWO",
            "source_references": [],
        },
    ]


async def main(email: str) -> int:
    if get_settings().app_env not in (AppEnv.development, AppEnv.testing):
        print("Refusing: this script only runs when APP_ENV is development or testing.")
        return 2
    async with AsyncSessionLocal() as db:
        user = (
            await db.execute(select(User).where(func.lower(User.email) == email.lower()))
        ).scalar_one_or_none()
        if user is None:
            print("No such user.")
            return 1
        ws = (
            (await db.execute(select(Workspace).where(Workspace.user_id == user.id)))
            .scalars()
            .first()
        )
        if ws is None:
            print("The user has no workspace.")
            return 1
        repo = StudyMaterialRepository(db)

        async def material(kind: str, title: str, payload: dict[str, Any]) -> Any:
            return await repo.create_with_first_version(
                user_id=user.id,
                workspace_id=ws.id,
                subject_id=None,
                chapter_id=None,
                title=title,
                resource_type=kind,
                status="completed",
                content={"payload": payload, "sources": SOURCES},
                generation_settings={},
                source_metadata={"documents": []},
            )

        summary = await material(
            "summary",
            "Cell energy summary",
            {
                "title": "Cell energy summary",
                "sections": [
                    {
                        "heading": "Mitochondria",
                        "kind": "concept",
                        "body": "Mitochondria make ATP.",
                        "bullets": ["Site of the Krebs cycle"],
                        "source_refs": [1],
                    },
                    {
                        "heading": "Chloroplasts",
                        "kind": "concept",
                        "body": "Chloroplasts capture light.",
                        "bullets": [],
                        "source_refs": [1],
                    },
                ],
            },
        )
        guide = await material(
            "study_guide",
            "Cell biology guide",
            {
                "title": "Cell biology guide",
                "overview": "How cells get energy.",
                "learning_objectives": [{"text": "Explain ATP production", "source_refs": [1]}],
                "prerequisites": [],
                "sections": [
                    {"heading": "Energy", "level": 1, "body": "Cells need ATP.", "bullets": []}
                ],
                "key_takeaways": ["Mitochondria make ATP"],
                "practice_questions": [],
            },
        )
        glossary = await material(
            "glossary",
            "Cell glossary",
            {
                "title": "Cell glossary",
                "terms": [
                    {
                        "term": "Mitochondrion",
                        "definition": "Organelle that produces ATP.",
                        "topic": "Organelles",
                        "source_refs": [1],
                    },
                    {
                        "term": "Chloroplast",
                        "definition": "Organelle where photosynthesis happens.",
                        "topic": "Organelles",
                        "source_refs": [1],
                    },
                    {
                        "term": "Osmosis",
                        "definition": "Movement of water across a membrane.",
                        "topic": "Transport",
                        "source_refs": [],
                    },
                ],
            },
        )
        formulas = await material(
            "formula_sheet",
            "Energy formulas",
            {
                "title": "Energy formulas",
                "verification": "unverified",
                "flagged_count": 1,
                "formulas": [
                    {
                        "name": "Mass-energy",
                        "expression": "E = mc^2",
                        "variables": [{"symbol": "E", "meaning": "energy", "unit": "J"}],
                        "source_refs": [1],
                    },
                    {
                        "name": "Broken",
                        "expression": "\\frac{1",
                        "needs_review": True,
                        "review_notes": ["syntax error"],
                        "variables": [],
                        "source_refs": [],
                    },
                ],
            },
        )
        deck_material = await material(
            "flashcards", "Cell flashcards", {"title": "Cell flashcards"}
        )
        cards = FlashcardRepository(db)
        deck = await cards.create_set(user.id, deck_material.id)
        await cards.add_cards(
            deck,
            [
                {
                    "front": f"Card question number {n}?",
                    "back": f"Card answer {n}",
                    "card_type": "basic",
                    "difficulty": "easy",
                    "origin": "generated",
                }
                for n in range(1, 4)
            ],
        )
        quizzes = QuizRepository(db)
        quiz_ids: dict[str, str] = {}
        for key, title, limit in (("quiz", "Cell quiz", None), ("timed_quiz", "Timed quiz", 4)):
            m = await material("quiz", title, {"title": title, "question_count": 2})
            q = await quizzes.create_quiz(
                user_id=user.id,
                material_id=m.id,
                title=title,
                description=None,
                time_limit=limit,
                settings={},
                questions=questions(),
            )
            quiz_ids[key] = str(m.id)
            quiz_ids[f"{key}_row"] = str(q.id)
        await db.commit()
        print(
            json.dumps(
                {
                    "summary": str(summary.id),
                    "study_guide": str(guide.id),
                    "glossary": str(glossary.id),
                    "formula_sheet": str(formulas.id),
                    "flashcards": str(deck_material.id),
                    **quiz_ids,
                }
            )
        )
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: seed_study_e2e.py <email>")
        sys.exit(2)
    sys.exit(asyncio.run(main(sys.argv[1])))
