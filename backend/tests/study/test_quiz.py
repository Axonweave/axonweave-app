"""Phase 4 M3: the quiz generator, answer-key validation, attempts, scoring, the server-side timer,
idempotent submit, ownership and the answer-key leakage sweep.

FakeProvider only: no network, no cost.
"""

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.models.quiz import Quiz, QuizAttempt, QuizAttemptAnswer, QuizQuestion
from tests.conftest import _TestSessionLocal
from tests.retrieval.test_search import Actor, add_doc
from tests.study.conftest import Harness, get_job
from tests.test_closeout_users_config import _call

LONG = "word " * 100
KEYS = ("EXPL-MC", "EXPL-MS", "EXPL-TF", "EXPL-FILL", "MODEL-SHORT", "MODEL-DESC", "RUBRIC-A")


def q(question: str, qtype: str, correct: list[str], **kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "question": question,
        "question_type": qtype,
        "difficulty": "medium",
        "options": [],
        "correct_answers": correct,
        "explanation": "",
        "rubric": [],
        "source_refs": [1],
    }
    base.update(kw)
    return base


def opts(*texts: str) -> list[dict[str, str]]:
    return [{"id": "ABCDEF"[i], "text": t} for i, t in enumerate(texts)]


MC = q(
    "Which organelle captures light energy for photosynthesis?",
    "multiple_choice",
    ["B"],
    options=opts("Nucleus", "Chloroplast", "Ribosome", "Vacuole"),
    explanation="EXPL-MC chloroplasts hold chlorophyll.",
)
MS = q(
    "Select all the products of the light reactions.",
    "multiple_select",
    ["A", "C"],
    options=opts("ATP", "Glucose", "NADPH", "Starch"),
    explanation="EXPL-MS both carry energy.",
    source_refs=[1, 99],
)
TF = q(
    "Mitochondria run the Krebs cycle.",
    "true_false",
    ["true"],
    explanation="EXPL-TF as stated.",
    source_refs=[2],
)
FILL = q(
    "The Krebs cycle takes place in the ___ of the cell.",
    "fill_in_the_blank",
    ["mitochondria", "mitochondrion"],
    explanation="EXPL-FILL .",
    source_refs=[2],
)
SHORT = q(
    "Briefly state what chloroplasts do for the plant.",
    "short_answer",
    ["MODEL-SHORT they turn light into sugar."],
    rubric=["RUBRIC-A mentions light"],
    source_refs=[1],
)
DESC = q(
    "Describe how the Krebs cycle connects to the rest of cell respiration.",
    "descriptive",
    ["MODEL-DESC it oxidises acetyl-CoA and feeds the electron transport chain."],
    rubric=["RUBRIC-A names acetyl-CoA", "Mentions the electron transport chain"],
    source_refs=[2],
)
ALL = [MC, MS, TF, FILL, SHORT, DESC]
ALL_TYPES = [
    "multiple_choice",
    "multiple_select",
    "true_false",
    "fill_in_the_blank",
    "short_answer",
    "descriptive",
]


def reply(questions: list[dict[str, Any]] | None = None) -> str:
    return json.dumps(
        {
            "title": "Cell energy quiz",
            "description": "Check yourself.",
            "questions": ALL if questions is None else questions,
        }
    )


async def make_quiz(
    client: AsyncClient,
    study: Harness,
    who: Actor,
    db: AsyncSession,
    questions: list[dict[str, Any]] | None = None,
    **settings: Any,
) -> tuple[dict[str, Any], str]:
    """Generate a quiz. Returns (job, quiz id)."""
    doc = await add_doc(
        db, who, "Biology", ["Photosynthesis in chloroplasts. " + LONG, "Krebs " + LONG]
    )
    study.provider.reply = reply(questions)
    settings.setdefault("question_types", ALL_TYPES)
    resp = await _call(
        client,
        who,
        "POST",
        "/study/generations",
        json={
            "generation_type": "quiz",
            "source": {"type": "document", "id": str(doc.id)},
            "settings": {"count": 10, **settings},
        },
    )
    assert resp.status_code == 202, resp.text
    job_id = resp.json()["data"]["id"]
    assert await study.run(job_id) == "completed"
    job = await get_job(client, who, job_id)
    async with _TestSessionLocal() as s:
        quiz_id = (
            await s.execute(
                select(Quiz.id).where(Quiz.study_material_id == uuid.UUID(job["study_material_id"]))
            )
        ).scalar_one()
    return job, str(quiz_id)


async def start(client: AsyncClient, who: Actor, quiz_id: str) -> dict[str, Any]:
    resp = await _call(client, who, "POST", f"/study/quizzes/{quiz_id}/attempts")
    assert resp.status_code in (200, 201), resp.text
    data: dict[str, Any] = resp.json()["data"]
    return data


def by_type(quiz: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {x["question_type"]: x for x in quiz["questions"]}


async def get_quiz(client: AsyncClient, who: Actor, quiz_id: str) -> dict[str, Any]:
    resp = await _call(client, who, "GET", f"/study/quizzes/{quiz_id}")
    assert resp.status_code == 200, resp.text
    data: dict[str, Any] = resp.json()["data"]
    return data


async def results(client: AsyncClient, who: Actor, quiz_id: str, attempt_id: str) -> Any:
    return await _call(client, who, "GET", f"/study/quizzes/{quiz_id}/results/{attempt_id}")


async def answer_all_right(
    client: AsyncClient, who: Actor, quiz_id: str, attempt: dict[str, Any]
) -> Any:
    t = by_type(attempt_quiz := await get_quiz(client, who, quiz_id))
    assert attempt_quiz
    body = [
        {"question_id": t["multiple_choice"]["id"], "answer": ["B"]},
        {"question_id": t["multiple_select"]["id"], "answer": ["C", "A"]},
        {"question_id": t["true_false"]["id"], "answer": ["true"]},
        {"question_id": t["fill_in_the_blank"]["id"], "answer": "  Mitochondria. "},
        {"question_id": t["short_answer"]["id"], "answer": "they make sugar"},
    ]
    return await _call(
        client,
        who,
        "PUT",
        f"/study/quizzes/{quiz_id}/attempts/{attempt['id']}/answers",
        json={"answers": body},
    )


async def expire(attempt_id: str, seconds_ago: int) -> None:
    async with _TestSessionLocal() as s:
        await s.execute(
            update(QuizAttempt)
            .where(QuizAttempt.id == uuid.UUID(attempt_id))
            .values(expires_at=datetime.now(UTC) - timedelta(seconds=seconds_ago))
        )
        await s.commit()


# generation ─────────────────────────────────────────────────────────────────


class TestGeneration:
    async def test_every_type_is_generated_and_keys_are_stored(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        job, quiz_id = await make_quiz(client, study, alice, db_session)
        quiz = await get_quiz(client, alice, quiz_id)
        assert quiz["question_count"] == 6
        assert set(by_type(quiz)) == set(ALL_TYPES)
        assert by_type(quiz)["true_false"]["options"] == [
            {"id": "true", "text": "True"},
            {"id": "false", "text": "False"},
        ]
        assert by_type(quiz)["multiple_select"]["answer_format"] == "multiple_choice"
        async with _TestSessionLocal() as s:
            rows = (await s.execute(select(QuizQuestion))).scalars().all()
        keyed = {r.question_type: r for r in rows}
        assert keyed["multiple_choice"].correct_answers == ["B"]
        assert keyed["multiple_select"].correct_answers == ["A", "C"]
        assert keyed["short_answer"].rubric == ["RUBRIC-A mentions light"]
        # the invented source number 99 is stripped, real ones map to a real chunk
        refs = keyed["multiple_select"].source_references
        assert [r["rank"] for r in refs] == [1] and refs[0]["chunk_id"]
        assert job["generation_type"] == "quiz"

    async def test_prompt_states_settings(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        await make_quiz(
            client, study, alice, db_session, count=7, difficulty="mixed", language="French"
        )
        turn = study.provider.calls[0].messages[0].content
        assert "at most 7 quiz questions" in turn and "French" in turn

    async def test_time_limit_and_randomise_are_stored(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        _, quiz_id = await make_quiz(
            client, study, alice, db_session, time_limit_minutes=5, randomize_order=True
        )
        quiz = await get_quiz(client, alice, quiz_id)
        assert quiz["time_limit_seconds"] == 300 and quiz["randomize_order"] is True

    async def test_unsupported_questions_are_dropped(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        stray = q(
            "Who painted the ceiling of the Sistine Chapel?",
            "true_false",
            ["false"],
            explanation="x",
            source_refs=[77],
        )
        _, quiz_id = await make_quiz(client, study, alice, db_session, [MC, stray])
        assert (await get_quiz(client, alice, quiz_id))["question_count"] == 1

    @pytest.mark.parametrize(
        "bad",
        [
            # MCQ with two correct answers
            {**MC, "correct_answers": ["A", "B"]},
            # MCQ whose answer is not an option
            {**MC, "correct_answers": ["F"]},
            # MCQ with duplicate option text
            {**MC, "options": opts("Nucleus", "Nucleus", "Ribosome", "Vacuole")},
            # MCQ with too few options
            {**MC, "options": opts("Nucleus", "Chloroplast")},
            # MCQ with no explanation
            {**MC, "explanation": ""},
            # multiple select with a single correct answer
            {**MS, "correct_answers": ["A"]},
            # multiple select where every option is correct
            {**MS, "correct_answers": ["A", "B", "C", "D"]},
            # true/false with a bad key
            {**TF, "correct_answers": ["maybe"]},
            # true/false with options
            {**TF, "options": opts("Yes", "No")},
            # fill-in with no blank
            {**FILL, "question": "The Krebs cycle takes place in the cell somewhere."},
            # fill-in that gives its answer away
            {**FILL, "question": "The mitochondria ___ hosts the Krebs cycle."},
            # short answer with no rubric
            {**SHORT, "rubric": []},
            # descriptive with one rubric point
            {**DESC, "rubric": ["only one"]},
            # written question with two model answers
            {**SHORT, "correct_answers": ["one", "two"]},
            # unknown field
            {**MC, "hint": "B"},
            # unrequested type (this run asks for objective types only)
            {**SHORT, "unrequested": True},
        ],
    )
    async def test_invalid_answer_keys_fail_safely(
        self,
        client: AsyncClient,
        study: Harness,
        alice: Actor,
        db_session: AsyncSession,
        bad: dict[str, Any],
    ) -> None:
        doc = await add_doc(db_session, alice, "Biology", ["Photosynthesis. " + LONG])
        study.provider.reply = reply([bad])
        types = ["multiple_choice", "multiple_select", "true_false", "fill_in_the_blank"]
        if bad["question_type"] in ("short_answer", "descriptive") and "unrequested" not in bad:
            types.append(bad["question_type"])
        resp = await _call(
            client,
            alice,
            "POST",
            "/study/generations",
            json={
                "generation_type": "quiz",
                "source": {"type": "document", "id": str(doc.id)},
                "settings": {"question_types": types},
            },
        )
        job_id = resp.json()["data"]["id"]
        assert await study.run(job_id) == "failed"
        assert len(study.provider.calls) == 2  # exactly one correction call
        job = await get_job(client, alice, job_id)
        assert job["error_code"] == "GENERATION_INVALID_OUTPUT" and job["study_material_id"] is None
        async with _TestSessionLocal() as s:
            assert (await s.execute(select(QuizQuestion))).first() is None

    async def test_near_duplicate_questions_get_one_correction(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        twin = {**MC, "question": "Which organelle captures the light energy for photosynthesis?"}
        doc = await add_doc(db_session, alice, "Biology", ["Photosynthesis. " + LONG])
        study.provider.reply = reply([MC, twin])
        resp = await _call(
            client,
            alice,
            "POST",
            "/study/generations",
            json={"generation_type": "quiz", "source": {"type": "document", "id": str(doc.id)}},
        )
        assert await study.run(resp.json()["data"]["id"]) == "failed"

    @pytest.mark.parametrize(
        "settings",
        [
            {"count": 0},
            {"count": 51},
            {"question_types": []},
            {"question_types": ["essay"]},
            {"difficulty": "extreme"},
            {"time_limit_minutes": 0},
            {"time_limit_minutes": 100000},
            {"show_explanations": "immediately"},
            {"unknown": 1},
        ],
    )
    async def test_settings_are_validated(
        self,
        client: AsyncClient,
        study: Harness,
        alice: Actor,
        db_session: AsyncSession,
        settings: dict[str, Any],
    ) -> None:
        doc = await add_doc(db_session, alice, "Biology", ["Photosynthesis. " + LONG])
        resp = await _call(
            client,
            alice,
            "POST",
            "/study/generations",
            json={
                "generation_type": "quiz",
                "source": {"type": "document", "id": str(doc.id)},
                "settings": settings,
            },
        )
        assert resp.status_code == 422


# attempts and scoring ───────────────────────────────────────────────────────


class TestAttempts:
    async def test_full_attempt_scores_objective_questions(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        _, quiz_id = await make_quiz(client, study, alice, db_session)
        attempt = await start(client, alice, quiz_id)
        assert attempt["status"] == "in_progress" and len(attempt["questions"]) == 6
        saved = await answer_all_right(client, alice, quiz_id, attempt)
        assert saved.status_code == 200
        done = await _call(
            client,
            alice,
            "POST",
            f"/study/quizzes/{quiz_id}/attempts/{attempt['id']}/submit",
            json={},
        )
        assert done.status_code == 200 and done.json()["data"]["status"] == "submitted"
        res = (await results(client, alice, quiz_id, attempt["id"])).json()["data"]
        assert (res["total_questions"], res["graded_questions"]) == (6, 4)
        assert (res["correct"], res["incorrect"], res["unanswered"], res["not_graded"]) == (
            4,
            0,
            1,
            1,
        )
        assert res["score"] == 4.0 and res["percentage"] == 100.0
        rows = {x["question_type"]: x for x in res["questions"]}
        assert rows["multiple_select"]["is_correct"] is True
        assert rows["multiple_choice"]["correct_answers"] == ["B"]
        assert rows["multiple_choice"]["explanation"].startswith("EXPL-MC")
        assert rows["short_answer"]["grading"] == "self_assessment"
        assert rows["short_answer"]["is_correct"] is None
        assert rows["short_answer"]["correct_answers"][0].startswith("MODEL-SHORT")
        assert rows["short_answer"]["rubric"] == ["RUBRIC-A mentions light"]
        assert rows["descriptive"]["answered"] is False
        assert rows["multiple_choice"]["source_references"]
        assert "mastery" in res["note"]

    async def test_wrong_answers_and_exact_match_for_multiple_select(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        _, quiz_id = await make_quiz(client, study, alice, db_session)
        attempt = await start(client, alice, quiz_id)
        t = by_type(await get_quiz(client, alice, quiz_id))
        body = {
            "answers": [
                {"question_id": t["multiple_choice"]["id"], "answer": ["A"]},
                {"question_id": t["multiple_select"]["id"], "answer": ["A"]},  # partial: no credit
                {"question_id": t["true_false"]["id"], "answer": ["false"]},
                {"question_id": t["fill_in_the_blank"]["id"], "answer": "chloroplast"},
            ]
        }
        done = await _call(
            client,
            alice,
            "POST",
            f"/study/quizzes/{quiz_id}/attempts/{attempt['id']}/submit",
            json=body,
        )
        assert done.status_code == 200
        res = (await results(client, alice, quiz_id, attempt["id"])).json()["data"]
        assert (res["correct"], res["incorrect"], res["score"], res["percentage"]) == (
            0,
            4,
            0.0,
            0.0,
        )
        assert all(x["awarded_score"] == 0 for x in res["questions"])

    async def test_results_are_persisted_per_question(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        _, quiz_id = await make_quiz(client, study, alice, db_session)
        attempt = await start(client, alice, quiz_id)
        await answer_all_right(client, alice, quiz_id, attempt)
        await _call(
            client,
            alice,
            "POST",
            f"/study/quizzes/{quiz_id}/attempts/{attempt['id']}/submit",
            json={},
        )
        async with _TestSessionLocal() as s:
            att = (await s.execute(select(QuizAttempt))).scalar_one()
            rows = (await s.execute(select(QuizAttemptAnswer))).scalars().all()
        assert att.status == "submitted" and float(att.score) == 4.0 and att.total_questions == 6
        assert len(rows) == 6
        assert sorted(r.is_correct for r in rows if r.is_correct is not None) == [True] * 4
        assert sum(1 for r in rows if r.is_correct is None) == 2  # both written questions
        # still there after a fresh read through the API
        res = (await results(client, alice, quiz_id, attempt["id"])).json()["data"]
        assert res["score"] == 4.0
        history = (await _call(client, alice, "GET", f"/study/quizzes/{quiz_id}/attempts")).json()
        assert history["data"]["total"] == 1 and history["data"]["items"][0]["percentage"] == 100.0

    async def test_answers_are_validated_against_the_question(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        _, quiz_id = await make_quiz(client, study, alice, db_session)
        attempt = await start(client, alice, quiz_id)
        t = by_type(await get_quiz(client, alice, quiz_id))
        url = f"/study/quizzes/{quiz_id}/attempts/{attempt['id']}/answers"
        bad_answers: list[dict[str, Any]] = [
            {"question_id": t["multiple_choice"]["id"], "answer": ["A", "B"]},  # two for single
            {"question_id": t["multiple_choice"]["id"], "answer": ["Z"]},  # unknown option
            {"question_id": t["multiple_choice"]["id"], "answer": "A"},  # wrong shape
            {"question_id": t["multiple_select"]["id"], "answer": ["A", "A"]},  # repeats
            {"question_id": t["fill_in_the_blank"]["id"], "answer": ["x"]},  # wrong shape
            {"question_id": t["fill_in_the_blank"]["id"], "answer": "x" * 501},  # too long
            {"question_id": str(uuid.uuid4()), "answer": "x"},  # not in this quiz
        ]
        for item in bad_answers:
            resp = await _call(client, alice, "PUT", url, json={"answers": [item]})
            assert resp.status_code == 422, item
        # an unknown body field is rejected too
        resp = await _call(client, alice, "PUT", url, json={"answers": [], "score": 6})
        assert resp.status_code == 422

    async def test_answers_survive_a_refresh_and_flags_are_kept(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        _, quiz_id = await make_quiz(client, study, alice, db_session)
        attempt = await start(client, alice, quiz_id)
        t = by_type(await get_quiz(client, alice, quiz_id))
        mc = t["multiple_choice"]["id"]
        await _call(
            client,
            alice,
            "PUT",
            f"/study/quizzes/{quiz_id}/attempts/{attempt['id']}/answers",
            json={
                "answers": [{"question_id": mc, "answer": ["C"]}],
                "flagged": [mc, str(uuid.uuid4())],
            },
        )
        again = await start(client, alice, quiz_id)  # resume, not a second attempt
        assert again["id"] == attempt["id"] and again["answers"][mc] == ["C"]
        assert again["flagged"] == [mc]
        got = (
            await _call(client, alice, "GET", f"/study/quizzes/{quiz_id}/attempts/{attempt['id']}")
        ).json()["data"]
        assert got["answers"][mc] == ["C"]

    async def test_retake_after_submit_starts_a_new_attempt(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        _, quiz_id = await make_quiz(client, study, alice, db_session)
        first = await start(client, alice, quiz_id)
        await _call(
            client,
            alice,
            "POST",
            f"/study/quizzes/{quiz_id}/attempts/{first['id']}/submit",
            json={},
        )
        resp = await _call(client, alice, "POST", f"/study/quizzes/{quiz_id}/attempts")
        assert resp.status_code == 201 and resp.json()["data"]["id"] != first["id"]
        assert resp.json()["data"]["answers"] == {}
        history = (await _call(client, alice, "GET", f"/study/quizzes/{quiz_id}/attempts")).json()
        assert history["data"]["total"] == 2

    async def test_randomised_order_is_fixed_per_attempt(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        _, quiz_id = await make_quiz(client, study, alice, db_session, randomize_order=True)
        attempt = await start(client, alice, quiz_id)
        assert sorted(attempt["question_order"]) == sorted(x["id"] for x in attempt["questions"])
        assert [x["id"] for x in attempt["questions"]] == attempt["question_order"]
        again = await start(client, alice, quiz_id)
        assert again["question_order"] == attempt["question_order"]


class TestSubmitAndTimer:
    async def test_double_submit_is_idempotent_and_answers_are_frozen(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        _, quiz_id = await make_quiz(client, study, alice, db_session)
        attempt = await start(client, alice, quiz_id)
        await answer_all_right(client, alice, quiz_id, attempt)
        base = f"/study/quizzes/{quiz_id}/attempts/{attempt['id']}"
        first = (await _call(client, alice, "POST", f"{base}/submit", json={})).json()["data"]
        t = by_type(await get_quiz(client, alice, quiz_id))
        # a second submit, even carrying different answers, changes nothing
        second = await _call(
            client,
            alice,
            "POST",
            f"{base}/submit",
            json={"answers": [{"question_id": t["true_false"]["id"], "answer": ["false"]}]},
        )
        assert second.status_code == 200
        assert second.json()["data"]["score"] == first["score"] == 4.0
        assert second.json()["data"]["submitted_at"] == first["submitted_at"]
        # no modification after submission
        late = await _call(
            client,
            alice,
            "PUT",
            f"{base}/answers",
            json={"answers": [{"question_id": t["true_false"]["id"], "answer": ["false"]}]},
        )
        assert (late.status_code, late.json()["error"]["code"]) == (409, "QUIZ_ATTEMPT_SUBMITTED")
        async with _TestSessionLocal() as s:
            assert len((await s.execute(select(QuizAttemptAnswer))).scalars().all()) == 6
        res = (await results(client, alice, quiz_id, attempt["id"])).json()["data"]
        assert res["score"] == 4.0

    async def test_results_need_a_submitted_attempt(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        _, quiz_id = await make_quiz(client, study, alice, db_session)
        attempt = await start(client, alice, quiz_id)
        resp = await results(client, alice, quiz_id, attempt["id"])
        assert (resp.status_code, resp.json()["error"]["code"]) == (
            409,
            "QUIZ_ATTEMPT_NOT_SUBMITTED",
        )

    async def test_timer_is_server_side(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        _, quiz_id = await make_quiz(client, study, alice, db_session, time_limit_minutes=10)
        attempt = await start(client, alice, quiz_id)
        assert 590 <= attempt["seconds_remaining"] <= 600
        assert attempt["expires_at"] and attempt["server_time"]
        untimed_job, untimed = await make_quiz(client, study, alice, db_session)
        assert untimed_job
        assert (await start(client, alice, untimed))["seconds_remaining"] is None

    async def test_expiry_submits_with_the_saved_answers(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        _, quiz_id = await make_quiz(client, study, alice, db_session, time_limit_minutes=10)
        attempt = await start(client, alice, quiz_id)
        t = by_type(await get_quiz(client, alice, quiz_id))
        base = f"/study/quizzes/{quiz_id}/attempts/{attempt['id']}"
        await _call(
            client,
            alice,
            "PUT",
            f"{base}/answers",
            json={"answers": [{"question_id": t["multiple_choice"]["id"], "answer": ["B"]}]},
        )
        await expire(attempt["id"], 60)
        # saving after the deadline is refused and the attempt is finalised
        late = await _call(
            client,
            alice,
            "PUT",
            f"{base}/answers",
            json={"answers": [{"question_id": t["true_false"]["id"], "answer": ["true"]}]},
        )
        assert (late.status_code, late.json()["error"]["code"]) == (409, "QUIZ_ATTEMPT_EXPIRED")
        res = (await results(client, alice, quiz_id, attempt["id"])).json()["data"]
        assert res["auto_submitted"] is True and res["score"] == 1.0  # only the saved answer
        assert res["unanswered"] == 5
        assert res["time_taken_seconds"] <= 600  # never longer than the limit

    async def test_late_submit_ignores_the_body_but_accepts_within_grace(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        _, quiz_id = await make_quiz(client, study, alice, db_session, time_limit_minutes=10)
        t = by_type(await get_quiz(client, alice, quiz_id))
        body = {"answers": [{"question_id": t["true_false"]["id"], "answer": ["true"]}]}
        # within the grace window the answers sent with the submit still count
        a = await start(client, alice, quiz_id)
        await expire(a["id"], 3)
        await _call(
            client, alice, "POST", f"/study/quizzes/{quiz_id}/attempts/{a['id']}/submit", json=body
        )
        res = (await results(client, alice, quiz_id, a["id"])).json()["data"]
        assert res["score"] == 1.0 and res["auto_submitted"] is True
        # far past the deadline they do not
        b = await start(client, alice, quiz_id)
        await expire(b["id"], 3600)
        await _call(
            client, alice, "POST", f"/study/quizzes/{quiz_id}/attempts/{b['id']}/submit", json=body
        )
        res = (await results(client, alice, quiz_id, b["id"])).json()["data"]
        assert res["score"] == 0.0

    async def test_starting_after_expiry_finalises_the_old_attempt(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        _, quiz_id = await make_quiz(client, study, alice, db_session, time_limit_minutes=10)
        old = await start(client, alice, quiz_id)
        await expire(old["id"], 30)
        new = await _call(client, alice, "POST", f"/study/quizzes/{quiz_id}/attempts")
        assert new.status_code == 201 and new.json()["data"]["id"] != old["id"]
        got = (
            await _call(client, alice, "GET", f"/study/quizzes/{quiz_id}/attempts/{old['id']}")
        ).json()["data"]
        assert got["status"] == "submitted" and got["auto_submitted"] is True

    async def test_get_after_expiry_reports_a_submitted_attempt(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        _, quiz_id = await make_quiz(client, study, alice, db_session, time_limit_minutes=10)
        a = await start(client, alice, quiz_id)
        await expire(a["id"], 30)
        got = (
            await _call(client, alice, "GET", f"/study/quizzes/{quiz_id}/attempts/{a['id']}")
        ).json()["data"]
        assert got["status"] == "submitted" and got["questions"] == []
        assert (await results(client, alice, quiz_id, a["id"])).status_code == 200


# ownership ──────────────────────────────────────────────────────────────────


class TestOwnership:
    async def test_another_user_gets_404_everywhere(
        self,
        client: AsyncClient,
        study: Harness,
        alice: Actor,
        bob: Actor,
        db_session: AsyncSession,
    ) -> None:
        _, quiz_id = await make_quiz(client, study, alice, db_session)
        attempt = await start(client, alice, quiz_id)
        aid = attempt["id"]
        qid = attempt["questions"][0]["id"]
        for method, url, body in (
            ("GET", f"/study/quizzes/{quiz_id}", None),
            ("POST", f"/study/quizzes/{quiz_id}/attempts", None),
            ("GET", f"/study/quizzes/{quiz_id}/attempts", None),
            ("GET", f"/study/quizzes/{quiz_id}/attempts/{aid}", None),
            (
                "PUT",
                f"/study/quizzes/{quiz_id}/attempts/{aid}/answers",
                {"answers": [{"question_id": qid, "answer": ["A"]}]},
            ),
            ("POST", f"/study/quizzes/{quiz_id}/attempts/{aid}/submit", {}),
            ("GET", f"/study/quizzes/{quiz_id}/results/{aid}", None),
        ):
            kwargs = {"json": body} if body is not None else {}
            resp = await _call(client, bob, method, url, **kwargs)
            assert resp.status_code == 404, (method, url, resp.status_code)
        # nothing changed for the owner
        mine = (
            await _call(client, alice, "GET", f"/study/quizzes/{quiz_id}/attempts/{aid}")
        ).json()["data"]
        assert mine["status"] == "in_progress" and mine["answers"] == {}

    async def test_an_attempt_cannot_be_used_through_another_quiz(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        _, quiz_a = await make_quiz(client, study, alice, db_session)
        _, quiz_b = await make_quiz(client, study, alice, db_session)
        attempt = await start(client, alice, quiz_a)
        for method, tail in (("GET", ""), ("POST", "/submit"), ("PUT", "/answers")):
            resp = await _call(
                client,
                alice,
                method,
                f"/study/quizzes/{quiz_b}/attempts/{attempt['id']}{tail}",
                **({"json": {}} if method != "GET" else {}),
            )
            assert resp.status_code == 404, (method, tail)
        assert (await results(client, alice, quiz_b, attempt["id"])).status_code == 404

    async def test_two_users_have_separate_attempts_on_their_own_quizzes(
        self,
        client: AsyncClient,
        study: Harness,
        alice: Actor,
        bob: Actor,
        db_session: AsyncSession,
    ) -> None:
        _, qa = await make_quiz(client, study, alice, db_session)
        _, qb = await make_quiz(client, study, bob, db_session)
        a, b = await start(client, alice, qa), await start(client, bob, qb)
        assert a["id"] != b["id"]
        assert (
            await _call(client, bob, "GET", f"/study/quizzes/{qa}/attempts/{a['id']}")
        ).status_code == 404

    async def test_login_required(self, client: AsyncClient, study: Harness) -> None:
        nil = "00000000-0000-0000-0000-000000000000"
        for method, url in (
            ("GET", f"/api/v1/study/quizzes/{nil}"),
            ("POST", f"/api/v1/study/quizzes/{nil}/attempts"),
            ("GET", f"/api/v1/study/quizzes/{nil}/attempts"),
            ("GET", f"/api/v1/study/quizzes/{nil}/attempts/{nil}"),
            ("PUT", f"/api/v1/study/quizzes/{nil}/attempts/{nil}/answers"),
            ("POST", f"/api/v1/study/quizzes/{nil}/attempts/{nil}/submit"),
            ("GET", f"/api/v1/study/quizzes/{nil}/results/{nil}"),
        ):
            assert (await client.request(method, url, json={})).status_code in (401, 403)


# answer-key leakage ─────────────────────────────────────────────────────────

FORBIDDEN = {"correct_answers", "rubric", "model_answer", "answer_key", "accepted_answers"}
RESULTS_PATH = "/api/v1/study/quizzes/{quiz_id}/results/{attempt_id}"


def _fields(schema: Any, spec: dict[str, Any], seen: set[str] | None = None) -> set[str]:
    """Every property name reachable from a response schema (follows $ref, arrays, unions)."""
    seen = set() if seen is None else seen
    found: set[str] = set()
    if isinstance(schema, dict):
        ref = schema.get("$ref")
        if ref:
            if ref in seen:
                return found
            seen.add(ref)
            return _fields(spec["components"]["schemas"][ref.split("/")[-1]], spec, seen)
        for name, sub in schema.get("properties", {}).items():
            found.add(name)
            found |= _fields(sub, spec, seen)
        for key in ("items", "additionalProperties"):
            found |= _fields(schema.get(key), spec, seen)
        for key in ("anyOf", "allOf", "oneOf"):
            for sub in schema.get(key, []):
                found |= _fields(sub, spec, seen)
    return found


def _response_fields(operation: dict[str, Any], spec: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for resp in operation.get("responses", {}).values():
        body = resp.get("content", {}).get("application/json", {}).get("schema")
        out |= _fields(body, spec)
    return out


class TestAnswerKeyLeakage:
    def test_no_response_schema_exposes_the_key_except_the_results_route(self) -> None:
        spec = app.openapi()
        checked = 0
        for path, ops in spec["paths"].items():
            for method, op in ops.items():
                if method not in ("get", "post", "put", "patch", "delete"):
                    continue
                fields = _response_fields(op, spec)
                is_results = path.endswith("/results/{attempt_id}") and "quizzes" in path
                if is_results:
                    assert FORBIDDEN & fields, "results must carry the key"
                    continue
                checked += 1
                assert not (FORBIDDEN & fields), (method, path, FORBIDDEN & fields)
                if "/study/quizzes" in path:
                    assert "explanation" not in fields, (method, path)
        assert checked > 40  # the sweep really walked the API

    def test_request_models_cannot_set_an_answer_key(self) -> None:
        spec = app.openapi()
        for path, ops in spec["paths"].items():
            if "/study/quizzes" not in path:
                continue
            for method, op in ops.items():
                body = op.get("requestBody", {}).get("content", {}).get("application/json", {})
                assert not (FORBIDDEN & _fields(body.get("schema"), spec)), (method, path)

    async def test_no_get_returns_a_key_value_before_submission(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        job, quiz_id = await make_quiz(client, study, alice, db_session)
        attempt = await start(client, alice, quiz_id)
        await answer_all_right(client, alice, quiz_id, attempt)
        material = job["study_material_id"]
        urls = [
            f"/study/quizzes/{quiz_id}",
            f"/study/quizzes/{quiz_id}/attempts",
            f"/study/quizzes/{quiz_id}/attempts/{attempt['id']}",
            f"/study/materials/{material}",
            f"/study/materials/{material}/versions",
            f"/study/materials/{material}/versions/1",
            f"/study/generations/{job['id']}",
            f"/study/generations/{job['id']}/preview",
            "/study/materials",
            "/study/generations",
        ]
        for url in urls:
            resp = await _call(client, alice, "GET", url)
            text = resp.text
            for marker in KEYS:
                assert marker not in text, (url, marker)
            for key in ("correct_answers", "rubric", "explanation"):
                assert f'"{key}"' not in text, (url, key)
        # the save and start responses do not leak either
        saved = await answer_all_right(client, alice, quiz_id, attempt)
        again = await _call(client, alice, "POST", f"/study/quizzes/{quiz_id}/attempts")
        for resp in (saved, again):
            assert not any(m in resp.text for m in KEYS)
            assert '"correct_answers"' not in resp.text
        # ... and the key only shows up in the results of the submitted attempt
        await _call(
            client,
            alice,
            "POST",
            f"/study/quizzes/{quiz_id}/attempts/{attempt['id']}/submit",
            json={},
        )
        final = await results(client, alice, quiz_id, attempt["id"])
        assert "EXPL-MC" in final.text and "MODEL-SHORT" in final.text

    async def test_submit_response_does_not_leak_the_key(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        _, quiz_id = await make_quiz(client, study, alice, db_session)
        attempt = await start(client, alice, quiz_id)
        done = await _call(
            client,
            alice,
            "POST",
            f"/study/quizzes/{quiz_id}/attempts/{attempt['id']}/submit",
            json={},
        )
        assert not any(m in done.text for m in KEYS)
        assert '"correct_answers"' not in done.text

    async def test_quiz_cannot_be_edited_or_regenerated_through_generic_routes(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        job, _ = await make_quiz(client, study, alice, db_session)
        mid = job["study_material_id"]
        edit = await _call(
            client,
            alice,
            "PATCH",
            f"/study/materials/{mid}",
            json={"expected_version": 1, "payload": {"title": "x"}},
        )
        assert edit.status_code in (409, 422)
        regen = await _call(client, alice, "POST", f"/study/materials/{mid}/regenerate", json={})
        assert regen.status_code in (409, 422)
