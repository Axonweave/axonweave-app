"""Phase 4 M4: study guide, glossary, formula sheet and question bank generators.

FakeProvider only: no network, no cost.
"""

import json
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.study.latex import check_latex, defined_symbol, variable_symbols
from tests.retrieval.test_search import Actor, add_doc
from tests.study.conftest import Harness, get_job
from tests.study.test_quiz import ALL, ALL_TYPES, MC
from tests.test_closeout_users_config import _call

LONG = "word " * 100


async def run_generation_for(
    client: AsyncClient,
    study: Harness,
    who: Actor,
    db: AsyncSession,
    kind: str,
    reply: Any,
    **settings: Any,
) -> tuple[str, dict[str, Any]]:
    doc = await add_doc(db, who, "Biology", ["Photosynthesis. " + LONG, "Krebs cycle. " + LONG])
    study.provider.reply = reply if isinstance(reply, str) else json.dumps(reply)
    resp = await _call(
        client,
        who,
        "POST",
        "/study/generations",
        json={
            "generation_type": kind,
            "source": {"type": "document", "id": str(doc.id)},
            "settings": settings,
        },
    )
    assert resp.status_code == 202, resp.text
    job_id = resp.json()["data"]["id"]
    outcome = await study.run(job_id)
    return outcome, await get_job(client, who, job_id)


async def material(client: AsyncClient, who: Actor, job: dict[str, Any]) -> dict[str, Any]:
    resp = await _call(client, who, "GET", f"/study/materials/{job['study_material_id']}")
    assert resp.status_code == 200, resp.text
    data: dict[str, Any] = resp.json()["data"]
    return data


# ── study guide (22.4) ───────────────────────────────────────────────────────


def guide(**override: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "title": "Cell energy guide",
        "overview": "How cells get energy.",
        "learning_objectives": [
            {"text": "Explain photosynthesis", "source_refs": [1]},
            {"text": "Plan a revision schedule", "source_refs": []},
        ],
        "prerequisites": ["Basic chemistry"],
        "sections": [
            {
                "heading": "Photosynthesis",
                "level": 1,
                "body": "Light to sugar.",
                "source_refs": [1],
            },
            {"heading": "Light reactions", "level": 2, "body": "ATP made.", "source_refs": [1, 99]},
            {"heading": "Krebs cycle", "level": 1, "bullets": ["Acetyl-CoA"], "source_refs": [2]},
        ],
        "key_takeaways": ["Chloroplasts capture light"],
        "practice_questions": [{"question": "What do chloroplasts do?", "source_refs": [1]}],
    }
    body.update(override)
    return body


class TestStudyGuide:
    async def test_guide_hierarchy_objectives_and_sources(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        outcome, job = await run_generation_for(
            client, study, alice, db_session, "study_guide", guide()
        )
        assert outcome == "completed"
        payload = (await material(client, alice, job))["content"]["payload"]
        assert [s["level"] for s in payload["sections"]] == [1, 2, 1]
        assert payload["sections"][1]["source_refs"] == [1]  # invalid number 99 stripped
        supported, unsupported = payload["learning_objectives"]
        assert supported["generated_recommendation"] is False
        assert unsupported["generated_recommendation"] is True  # clearly marked (8.4)
        assert payload["practice_questions"][0]["question"]
        assert "answer" not in payload["practice_questions"][0]

    async def test_skipped_heading_level_fails(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        bad = guide(
            sections=[
                {"heading": "A", "level": 1, "body": "x", "source_refs": [1]},
                {"heading": "B", "level": 3, "body": "y", "source_refs": [1]},
            ]
        )
        outcome, job = await run_generation_for(
            client, study, alice, db_session, "study_guide", bad
        )
        assert outcome == "failed"
        assert job["status"] == "failed"

    async def test_guide_with_no_source_support_fails(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        bad = guide(sections=[{"heading": "A", "level": 1, "body": "x", "source_refs": [42]}])
        outcome, _ = await run_generation_for(client, study, alice, db_session, "study_guide", bad)
        assert outcome == "failed"

    async def test_settings_toggle_and_unknown_setting(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        outcome, job = await run_generation_for(
            client,
            study,
            alice,
            db_session,
            "study_guide",
            guide(),
            level="beginner",
            include_objectives=False,
            include_practice_questions=False,
        )
        assert outcome == "completed"
        payload = (await material(client, alice, job))["content"]["payload"]
        assert payload["learning_objectives"] == [] and payload["practice_questions"] == []
        doc = await add_doc(db_session, alice, "Other", [LONG])
        resp = await _call(
            client,
            alice,
            "POST",
            "/study/generations",
            json={
                "generation_type": "study_guide",
                "source": {"type": "document", "id": str(doc.id)},
                "settings": {"level": "expert"},
            },
        )
        assert resp.status_code == 422

    async def test_edit_keeps_hierarchy_rules_and_version(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        _, job = await run_generation_for(client, study, alice, db_session, "study_guide", guide())
        mat = await material(client, alice, job)
        payload = mat["content"]["payload"]
        payload["sections"][1]["level"] = 3  # level 1 -> 3 skips a level
        bad = await _call(
            client,
            alice,
            "PATCH",
            f"/study/materials/{mat['id']}",
            json={"expected_version": mat["current_version"], "payload": payload},
        )
        assert bad.status_code == 422, bad.text
        payload["sections"][1]["level"] = 2
        payload["sections"][1]["body"] = "Edited body."
        ok = await _call(
            client,
            alice,
            "PATCH",
            f"/study/materials/{mat['id']}",
            json={"expected_version": mat["current_version"], "payload": payload},
        )
        assert ok.status_code == 200, ok.text
        assert ok.json()["data"]["content"]["payload"]["sections"][1]["body"] == "Edited body."


# ── glossary (22.5) ──────────────────────────────────────────────────────────


def glossary(**override: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "title": "Biology terms",
        "terms": [
            {
                "term": "Photosynthesis",
                "definition": "Conversion of light into chemical energy.",
                "related_terms": ["Chloroplast", "Photosynthesis"],
                "topic": "Plants",
                "source_refs": [1],
            },
            {
                "term": "krebs cycle",
                "definition": "Oxidises acetyl-CoA.",
                "topic": "Respiration",
                "source_refs": [2],
            },
            {
                "term": " Photosynthesis. ",
                "definition": "A second, different wording.",
                "related_terms": ["ATP"],
                "source_refs": [2, 99],
            },
            {"term": "Unsupported", "definition": "No source.", "source_refs": [77]},
        ],
    }
    body.update(override)
    return body


class TestGlossary:
    async def test_terms_merged_sorted_and_referenced(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        outcome, job = await run_generation_for(
            client, study, alice, db_session, "glossary", glossary()
        )
        assert outcome == "completed"
        terms = (await material(client, alice, job))["content"]["payload"]["terms"]
        assert [t["term"] for t in terms] == ["krebs cycle", "Photosynthesis"]  # sorted, no dupes
        photo = terms[1]
        assert photo["definition"] == "Conversion of light into chemical energy."  # first wins
        assert photo["source_refs"] == [1, 2]
        assert photo["related_terms"] == ["Chloroplast", "ATP"]  # no self reference, merged
        assert all(t["source_refs"] for t in terms)  # unsupported term dropped

    async def test_search_filter_sort_endpoint(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        _, job = await run_generation_for(client, study, alice, db_session, "glossary", glossary())
        url = f"/study/materials/{job['study_material_id']}/glossary"
        hit = (await _call(client, alice, "GET", url, params={"q": "ACETYL"})).json()
        assert [t["term"] for t in hit["data"]] == ["krebs cycle"]
        topic = (await _call(client, alice, "GET", url, params={"topic": "plants"})).json()
        assert [t["term"] for t in topic["data"]] == ["Photosynthesis"]
        desc = (await _call(client, alice, "GET", url, params={"order": "desc"})).json()
        assert [t["term"] for t in desc["data"]] == ["Photosynthesis", "krebs cycle"]
        none = (await _call(client, alice, "GET", url, params={"q": "zzz"})).json()
        assert none["total"] == 0
        bad = await _call(client, alice, "GET", url, params={"order": "sideways"})
        assert bad.status_code == 422

    async def test_search_is_owner_scoped_and_type_checked(
        self,
        client: AsyncClient,
        study: Harness,
        alice: Actor,
        bob: Actor,
        db_session: AsyncSession,
    ) -> None:
        _, job = await run_generation_for(client, study, alice, db_session, "glossary", glossary())
        url = f"/study/materials/{job['study_material_id']}/glossary"
        assert (await _call(client, bob, "GET", url)).status_code == 404
        # a material of another type is not a glossary
        _, g = await run_generation_for(client, study, alice, db_session, "study_guide", guide())
        wrong = f"/study/materials/{g['study_material_id']}/glossary"
        assert (await _call(client, alice, "GET", wrong)).status_code == 404
        bank = f"/study/materials/{g['study_material_id']}/questions"
        assert (await _call(client, alice, "GET", bank)).status_code == 404

    async def test_edit_merges_duplicates(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        _, job = await run_generation_for(client, study, alice, db_session, "glossary", glossary())
        mat = await material(client, alice, job)
        payload = mat["content"]["payload"]
        payload["terms"].append(
            {"term": "ATP", "definition": "Energy currency.", "source_refs": [1]}
        )
        payload["terms"].append({"term": "atp", "definition": "dup", "source_refs": [2]})
        resp = await _call(
            client,
            alice,
            "PATCH",
            f"/study/materials/{mat['id']}",
            json={"expected_version": mat["current_version"], "payload": payload},
        )
        assert resp.status_code == 200, resp.text
        names = [t["term"] for t in resp.json()["data"]["content"]["payload"]["terms"]]
        assert [n.casefold() for n in names].count("atp") == 1


# ── formula sheet (22.6) ─────────────────────────────────────────────────────


def formula(name: str, expr: str, symbols: list[str], refs: list[int] | None = None) -> dict:
    return {
        "name": name,
        "expression": expr,
        "explanation": "From the text.",
        "variables": [{"symbol": s, "meaning": f"meaning of {s}", "unit": ""} for s in symbols],
        "source_refs": [1] if refs is None else refs,
    }


class TestLatexChecker:
    def test_valid_expressions(self) -> None:
        for expr in (
            r"E = mc^2",
            r"\frac{a}{b} + \sqrt{x^{2}}",
            r"$$\int_0^1 x\,dx$$",
            r"\begin{cases} x & y \\ z & w \end{cases}",
            r"\left( a + b \right)",
        ):
            assert check_latex(expr).ok, expr

    def test_delimiters_are_stripped(self) -> None:
        assert check_latex("$$a+b$$").expression == "a+b"
        assert check_latex(r"\(a+b\)").expression == "a+b"

    @pytest.mark.parametrize(
        ("expr", "issue"),
        [
            (r"\frac{a}{b", "unbalanced_braces"),
            (r"a}{b", "unbalanced_braces"),
            (r"\begin{cases} x", "mismatched_environment"),
            (r"\begin{cases} x \end{matrix}", "mismatched_environment"),
            (r"\begin{evil} x \end{evil}", "unknown_environment"),
            (r"\left( a", "unbalanced_left_right"),
            ("a + $b", "stray_dollar"),
        ],
    )
    def test_syntax_problems_are_flagged_not_dangerous(self, expr: str, issue: str) -> None:
        result = check_latex(expr)
        assert not result.dangerous
        assert issue in result.issues

    @pytest.mark.parametrize(
        "expr",
        [
            r"\href{http://evil}{x}",
            r"\url{http://evil}",
            r"\input{/etc/passwd}",
            r"\write18{rm}",
            r"\def\x{1}",
            r"\newcommand{\x}{1}",
            r"\includegraphics{a.png}",
            r"\htmlClass{x}{y}",
            "x <script>alert(1)</script>",
            "x <img src=a onerror=b>",
            "javascript:alert(1)",
            "x &#60; y",
            "",
            "a" * 700,
        ],
    )
    def test_dangerous_expressions_are_rejected(self, expr: str) -> None:
        assert check_latex(expr).dangerous

    def test_inequality_is_not_html(self) -> None:
        assert check_latex(r"a < b > c").ok

    def test_variable_symbols(self) -> None:
        assert variable_symbols(r"F = m a") == {"F", "m", "a"}
        assert variable_symbols(r"\sin\theta + v_0 \text{ m/s}") == {"\\theta", "v"}
        assert defined_symbol("$v_0$") == "v"
        assert defined_symbol("alpha") == "\\alpha"
        assert defined_symbol(r"\alpha") == "\\alpha"


class TestFormulaSheet:
    async def test_variables_flags_and_never_verified(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        reply = {
            "title": "Physics",
            "formulas": [
                formula("Newton second law", "$F = m a$", ["F", "m", "a"]),
                formula("Mass energy", "E = m c^2", ["E", "m"]),  # c undefined
                formula("Broken", r"\frac{a}{b", ["a", "b"]),  # bad syntax
                formula("Evil", r"\href{http://x}{y}", []),  # dropped
                formula("Unsourced", "x = y", ["x", "y"], refs=[50]),  # dropped
            ],
        }
        outcome, job = await run_generation_for(
            client, study, alice, db_session, "formula_sheet", reply
        )
        assert outcome == "completed"
        payload = (await material(client, alice, job))["content"]["payload"]
        by_name = {f["name"]: f for f in payload["formulas"]}
        assert set(by_name) == {"Newton second law", "Mass energy", "Broken"}
        newton = by_name["Newton second law"]
        assert newton["expression"] == "F = m a" and newton["needs_review"] is False
        assert by_name["Mass energy"]["review_notes"] == ["undefined_variables"]
        assert "unbalanced_braces" in by_name["Broken"]["review_notes"]
        assert payload["verification"] == "unverified"
        assert payload["flagged_count"] == 2
        assert newton["source_refs"] == [1]

    async def test_model_cannot_pre_approve_a_formula(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        f = formula("Mass energy", "E = m c^2", ["E", "m"])
        f["needs_review"] = False
        f["review_notes"] = []
        outcome, job = await run_generation_for(
            client, study, alice, db_session, "formula_sheet", {"title": "P", "formulas": [f]}
        )
        assert outcome == "completed"
        out = (await material(client, alice, job))["content"]["payload"]["formulas"][0]
        assert out["needs_review"] is True  # recomputed by the backend

    async def test_only_unsafe_formulas_fails_the_job(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        reply = {"title": "P", "formulas": [formula("Evil", r"\input{x}", [])]}
        outcome, _ = await run_generation_for(
            client, study, alice, db_session, "formula_sheet", reply
        )
        assert outcome == "failed"

    async def test_edit_rejects_unsafe_expression_and_reflags(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        reply = {"title": "P", "formulas": [formula("Force", "F = m a", ["F", "m", "a"])]}
        _, job = await run_generation_for(client, study, alice, db_session, "formula_sheet", reply)
        mat = await material(client, alice, job)
        payload = mat["content"]["payload"]
        payload["formulas"][0]["expression"] = r"\href{http://evil}{F}"
        bad = await _call(
            client,
            alice,
            "PATCH",
            f"/study/materials/{mat['id']}",
            json={"expected_version": mat["current_version"], "payload": payload},
        )
        assert bad.status_code == 422
        payload["formulas"][0]["expression"] = r"F = \frac{m}{a"
        ok = await _call(
            client,
            alice,
            "PATCH",
            f"/study/materials/{mat['id']}",
            json={"expected_version": mat["current_version"], "payload": payload},
        )
        assert ok.status_code == 200, ok.text
        saved = ok.json()["data"]["content"]["payload"]["formulas"][0]
        assert saved["needs_review"] is True


# ── question bank (11, 22.3 key protection) ──────────────────────────────────

SECRETS = ("EXPL-MC", "EXPL-MS", "EXPL-TF", "EXPL-FILL", "MODEL-SHORT", "MODEL-DESC", "RUBRIC-A")


def bank_questions() -> list[dict[str, Any]]:
    out = []
    for i, q in enumerate(ALL):
        out.append({**q, "topic": "Photosynthesis" if i % 2 == 0 else "Respiration"})
    out[0]["difficulty"] = "easy"
    out[1]["difficulty"] = "hard"
    return out


class TestQuestionBank:
    async def test_organised_by_topic_and_difficulty_without_keys(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        reply = {"title": "Cell bank", "questions": bank_questions()}
        outcome, job = await run_generation_for(
            client,
            study,
            alice,
            db_session,
            "question_bank",
            reply,
            count=10,
            question_types=ALL_TYPES,
        )
        assert outcome == "completed"
        resp = await _call(client, alice, "GET", f"/study/materials/{job['study_material_id']}")
        text = resp.text
        for secret in SECRETS:
            assert secret not in text
        assert "correct_answers" not in text and "rubric" not in text
        payload = resp.json()["data"]["content"]["payload"]
        assert payload["question_count"] == 6
        topics = {g["topic"]: g["difficulty"] for g in payload["organisation"]}
        assert set(topics) == {"Photosynthesis", "Respiration"}
        assert topics["Photosynthesis"]["easy"] == [0]
        # every index in the outline points at a real question of that topic and difficulty
        for group in payload["organisation"]:
            for diff, idx in group["difficulty"].items():
                for i in idx:
                    q = payload["questions"][i]
                    assert (q["topic"], q["difficulty"]) == (group["topic"], diff)
        assert all(q["origin"] == "generated" for q in payload["questions"])

    async def test_keys_are_stored_for_later_quizzes_and_never_in_the_job(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        from sqlalchemy import select

        from app.models.quiz import Quiz, QuizQuestion

        reply = {"title": "Cell bank", "questions": bank_questions()}
        _, job = await run_generation_for(
            client, study, alice, db_session, "question_bank", reply, question_types=ALL_TYPES
        )
        assert not any(s in json.dumps(job) for s in SECRETS)
        import uuid

        from tests.conftest import _TestSessionLocal

        async with _TestSessionLocal() as s:
            quiz = (
                await s.execute(
                    select(Quiz).where(
                        Quiz.study_material_id == uuid.UUID(job["study_material_id"])
                    )
                )
            ).scalar_one()
            assert quiz.time_limit is None
            rows = (
                (await s.execute(select(QuizQuestion).where(QuizQuestion.quiz_id == quiz.id)))
                .scalars()
                .all()
            )
            assert len(rows) == 6 and all(r.correct_answers for r in rows)

    async def test_reuses_quiz_validation(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        bad = {**MC, "correct_answers": ["Z"], "topic": "T"}  # not an option
        outcome, _ = await run_generation_for(
            client, study, alice, db_session, "question_bank", {"title": "B", "questions": [bad]}
        )
        assert outcome == "failed"
        dup = {"title": "B", "questions": [{**MC, "topic": "T"}, {**MC, "topic": "U"}]}
        outcome, _ = await run_generation_for(
            client, study, alice, db_session, "question_bank", dup
        )
        assert outcome == "failed"  # duplicates are not allowed (11.4)

    async def test_filter_endpoint_and_default_topic(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        qs = bank_questions()
        qs[2].pop("topic")
        reply = {"title": "Cell bank", "questions": qs}
        _, job = await run_generation_for(
            client, study, alice, db_session, "question_bank", reply, question_types=ALL_TYPES
        )
        url = f"/study/materials/{job['study_material_id']}/questions"
        everything = (await _call(client, alice, "GET", url)).json()
        assert everything["total"] == 6
        assert "General" in {q["topic"] for q in everything["data"]}
        hard = (await _call(client, alice, "GET", url, params={"difficulty": "hard"})).json()
        assert [q["question_type"] for q in hard["data"]] == ["multiple_select"]
        typed = (
            await _call(client, alice, "GET", url, params={"question_type": "true_false"})
        ).json()
        assert typed["total"] == 1
        search = (await _call(client, alice, "GET", url, params={"q": "krebs"})).json()
        assert search["total"] >= 1
        for page in (everything, hard, typed, search):
            assert not any(s in json.dumps(page) for s in SECRETS)
            assert "correct_answers" not in json.dumps(page)

    async def test_bank_is_owner_scoped_and_not_generically_editable(
        self,
        client: AsyncClient,
        study: Harness,
        alice: Actor,
        bob: Actor,
        db_session: AsyncSession,
    ) -> None:
        reply = {"title": "Cell bank", "questions": bank_questions()}
        _, job = await run_generation_for(
            client, study, alice, db_session, "question_bank", reply, question_types=ALL_TYPES
        )
        mid = job["study_material_id"]
        assert (
            await _call(client, bob, "GET", f"/study/materials/{mid}/questions")
        ).status_code == 404
        mat = await material(client, alice, job)
        patch = await _call(
            client,
            alice,
            "PATCH",
            f"/study/materials/{mid}",
            json={"expected_version": mat["current_version"], "payload": {"title": "x"}},
        )
        assert patch.status_code in (409, 422)  # item stores are edited through their own API


class TestRegistry:
    async def test_all_four_generators_are_listed_with_settings_schemas(
        self, client: AsyncClient, study: Harness, alice: Actor
    ) -> None:
        resp = await _call(client, alice, "GET", "/study/generators")
        assert resp.status_code == 200
        listed = {g["key"]: g for g in resp.json()["data"]}
        for key in ("study_guide", "glossary", "formula_sheet", "question_bank"):
            assert key in listed
            assert listed[key]["settings_schema"]["additionalProperties"] is False

    def test_prompts_are_versioned_and_registered(self) -> None:
        from app.ai.prompts.registry import active_prompt

        for key in ("study_guide", "study_glossary", "study_formula_sheet", "study_question_bank"):
            p = active_prompt(key)
            assert p.version == 1 and "untrusted data" in p.content
