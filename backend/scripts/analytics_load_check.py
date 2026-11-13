"""Time the Phase 5 analytics and quiz-history queries on a large amount of generated data.

Phase 5 acceptance asks for a check on thousands of attempts (`PHASE5_ACCEPTANCE.md`). This script
adds N submitted attempts (10 answers each, five topics, spread over a year) for ONE existing
user, times each analytics method and the history query, then removes what it added. Generated data
only, no model call. It refuses to run unless APP_ENV is `development` or `testing`.

  docker compose exec -T backend python scripts/analytics_load_check.py user@example.com [attempts]

Prints one line per query with the time in milliseconds. It prints no content or ids.
"""

import asyncio
import logging
import random
import sys
import time
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, func, insert, select  # noqa: E402
from sqlalchemy.orm import selectinload  # noqa: E402

from app.core.config import AppEnv, get_settings  # noqa: E402
from app.database.connection import AsyncSessionLocal  # noqa: E402
from app.models.quiz import Quiz, QuizAttempt, QuizAttemptAnswer, QuizQuestion  # noqa: E402
from app.models.study_material import StudyMaterial  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.workspace import Workspace  # noqa: E402
from app.modules.analytics.service import AnalyticsService  # noqa: E402
from app.modules.study.quiz_service import QuizService  # noqa: E402
from app.repositories.quiz_repository import QuizRepository  # noqa: E402
from app.repositories.study_material_repository import StudyMaterialRepository  # noqa: E402

QUESTIONS = 10
TOPICS = 5
CHUNK = 500
TITLE = "LOAD-CHECK quiz (temporary)"


def question(n: int) -> dict[str, Any]:
    return {
        "question": f"Load check question {n}?",
        "question_type": "multiple_choice",
        "difficulty": "easy",
        "options": [{"id": "A", "text": "One"}, {"id": "B", "text": "Two"}],
        "correct_answers": ["A"],
        "rubric": [],
        "explanation": None,
        "source_references": [],
        "topic": f"Load topic {n % TOPICS}",
    }


async def timed(label: str, call: Any) -> float:
    start = time.perf_counter()
    result = await call()
    ms = (time.perf_counter() - start) * 1000
    size = len(result) if hasattr(result, "__len__") else ""
    print(f"{label:<28}{ms:9.0f} ms  {size}")
    return ms


async def main(email: str, attempts: int) -> int:
    settings = get_settings()
    if settings.app_env not in (AppEnv.development, AppEnv.testing):
        print("Refusing: this script only runs when APP_ENV is development or testing.")
        return 2
    # engine echo is on in development; thousands of bulk rows would flood the output
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    rng = random.Random(7)  # noqa: S311 - repeatable fake data, not a security use
    async with AsyncSessionLocal() as db:
        user = (
            await db.execute(select(User).where(func.lower(User.email) == email.lower()))
        ).scalar_one_or_none()
        ws = (
            None
            if user is None
            else (await db.execute(select(Workspace).where(Workspace.user_id == user.id)))
            .scalars()
            .first()
        )
        if user is None or ws is None:
            print("No such user, or the user has no workspace.")
            return 1

        material = await StudyMaterialRepository(db).create_with_first_version(
            user_id=user.id,
            workspace_id=ws.id,
            subject_id=None,
            chapter_id=None,
            title=TITLE,
            resource_type="quiz",
            status="completed",
            content={"payload": {"title": TITLE}, "sources": []},
            generation_settings={},
            source_metadata={"documents": []},
        )
        quiz = await QuizRepository(db).create_quiz(
            user_id=user.id,
            material_id=material.id,
            title=TITLE,
            description=None,
            time_limit=None,
            settings={},
            questions=[question(n) for n in range(QUESTIONS)],
        )
        question_ids = [
            q.id
            for q in (
                await db.execute(
                    select(QuizQuestion)
                    .where(QuizQuestion.quiz_id == quiz.id)
                    .order_by(QuizQuestion.display_order)
                )
            ).scalars()
        ]
        quiz_id = quiz.id
        material_id = material.id
        user_id = user.id  # read before commits expire the object
        await db.commit()

        user_obj = user
        now = datetime.now(UTC)
        try:
            print(f"Seeding {attempts} attempts x {QUESTIONS} answers ...")
            for base in range(0, attempts, CHUNK):
                attempt_rows: list[dict[str, Any]] = []
                answer_rows: list[dict[str, Any]] = []
                for _ in range(min(CHUNK, attempts - base)):
                    attempt_id = uuid.uuid4()
                    submitted = now - timedelta(
                        days=rng.randint(0, 364), minutes=rng.randint(0, 1439)
                    )
                    correct = 0
                    for qid in question_ids:
                        ok = rng.random() < 0.6
                        correct += ok
                        answer_rows.append(
                            {
                                "user_id": user_id,
                                "attempt_id": attempt_id,
                                "question_id": qid,
                                "submitted_answer": ["A" if ok else "B"],
                                "is_correct": ok,
                                "awarded_score": Decimal(1 if ok else 0),
                                "max_score": Decimal(1),
                                "submitted_at": submitted,
                            }
                        )
                    attempt_rows.append(
                        {
                            "id": attempt_id,
                            "user_id": user_id,
                            "quiz_id": quiz_id,
                            "status": "submitted",
                            "question_order": [str(q) for q in question_ids],
                            "answers": {},
                            "flagged": [],
                            "started_at": submitted - timedelta(minutes=5),
                            "submitted_at": submitted,
                            "score": Decimal(correct),
                            "total_questions": QUESTIONS,
                            "graded_questions": QUESTIONS,
                            "percentage": Decimal(correct * 100 // QUESTIONS),
                            "correct_answers": correct,
                            "incorrect_answers": QUESTIONS - correct,
                            "unanswered": 0,
                            "max_score": Decimal(QUESTIONS),
                            "time_taken_seconds": 300,
                            "evaluation_status": "not_required",
                        }
                    )
                await db.execute(insert(QuizAttempt), attempt_rows)
                await db.execute(insert(QuizAttemptAnswer), answer_rows)
                await db.commit()

            total = (
                await db.execute(
                    select(func.count())
                    .select_from(QuizAttempt)
                    .where(QuizAttempt.user_id == user_id)
                )
            ).scalar_one()
            print(f"The user now has {total} attempts in total.\n")

            # load the user the way the request path does (profile eagerly, for the timezone)
            user_obj = (
                await db.execute(
                    select(User)
                    .options(selectinload(User.profile))
                    .where(User.id == user_id)
                    .execution_options(populate_existing=True)
                )
            ).scalar_one()
            analytics = AnalyticsService(db, settings)
            quiz_service = QuizService(db)
            slowest = 0.0
            none: dict[str, Any] = {
                "subject_id": None,
                "chapter_id": None,
                "start": None,
                "end": None,
            }
            for label, call in (
                ("overview", lambda: analytics.overview(user_obj, **none)),
                (
                    "quiz-performance (50)",
                    lambda: analytics.quiz_performance(user_obj, limit=50, **none),
                ),
                ("subject-performance", lambda: analytics.subject_performance(user_obj, **none)),
                ("topic-performance", lambda: analytics.topic_performance(user_obj, **none)),
                ("revision-activity", lambda: analytics.revision_activity(user_obj, **none)),
                ("study-calendar", lambda: analytics.calendar(user_obj, **none)),
                ("streaks", lambda: analytics.streaks(user_obj)),
                (
                    "quiz history (page of 20)",
                    lambda: quiz_service.history(
                        user_obj,
                        quiz_id=None,
                        subject_id=None,
                        chapter_id=None,
                        status=None,
                        date_from=None,
                        date_to=None,
                        limit=20,
                        offset=0,
                    ),
                ),
            ):
                slowest = max(slowest, await timed(label, call))
            print(f"\nSlowest query: {slowest:.0f} ms")
        finally:
            await db.rollback()
            await db.execute(delete(Quiz).where(Quiz.id == quiz_id))  # attempts cascade
            await db.execute(delete(StudyMaterial).where(StudyMaterial.id == material_id))
            await db.commit()
            left = (
                await db.execute(select(func.count()).select_from(Quiz).where(Quiz.id == quiz_id))
            ).scalar_one()
            print(f"Cleanup done, temporary quizzes left: {left}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        print("usage: analytics_load_check.py <email> [attempts]")
        sys.exit(2)
    sys.exit(asyncio.run(main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) == 3 else 3000)))
