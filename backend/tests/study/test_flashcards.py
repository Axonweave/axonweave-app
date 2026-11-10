"""Phase 4 M2: the flashcard generator, near-duplicate detection, quality rules, source references,
editing, reorder, regenerate-selected preview, quotas and ownership.

FakeProvider only: no network, no cost.
"""

import json
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.study.validation import find_near_duplicates, similarity
from tests.retrieval.test_search import Actor, add_doc
from tests.study.conftest import Harness, get_job
from tests.test_closeout_users_config import _call

LONG = "word " * 100


def card(front: str, back: str, **kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "front": front,
        "back": back,
        "card_type": "basic",
        "difficulty": "medium",
        "explanation": "Because the material says so.",
        "source_refs": [1],
    }
    base.update(kw)
    return base


GOOD_CARDS = [
    card("What do chloroplasts capture?", "Light energy.", source_refs=[1, 99]),
    card(
        "Define the Krebs cycle.",
        "Oxidation of acetyl-CoA.",
        card_type="definition",
        source_refs=[2],
    ),
    card(
        "The Krebs cycle runs in the ___.",
        "mitochondria",
        card_type="fill_in_the_blank",
        difficulty="easy",
        source_refs=[2],
    ),
]


def reply(cards: list[dict[str, Any]] | None = None, title: str = "Cell energy") -> str:
    return json.dumps({"title": title, "cards": cards if cards is not None else GOOD_CARDS})


async def make_deck(
    client: AsyncClient,
    study: Harness,
    who: Actor,
    db: AsyncSession,
    cards: list[dict[str, Any]] | None = None,
    **settings: Any,
) -> tuple[Any, dict[str, Any], dict[str, Any]]:
    """Generate a deck. Returns (document, job, flashcard set payload)."""
    doc = await add_doc(
        db, who, "Biology", ["Photosynthesis in chloroplasts. " + LONG, "Krebs. " + LONG]
    )
    study.provider.reply = reply(cards)
    resp = await _call(
        client,
        who,
        "POST",
        "/study/generations",
        json={
            "generation_type": "flashcards",
            "source": {"type": "document", "id": str(doc.id)},
            "settings": {"count": 10, **settings},
        },
    )
    assert resp.status_code == 202, resp.text
    job_id = resp.json()["data"]["id"]
    assert await study.run(job_id) == "completed"
    job = await get_job(client, who, job_id)
    return doc, job, await deck_of(client, who, job)


async def deck_of(client: AsyncClient, who: Actor, job: dict[str, Any]) -> dict[str, Any]:
    mat = await _call(client, who, "GET", f"/study/materials/{job['study_material_id']}")
    assert mat.status_code == 200
    set_id = await set_id_for(client, who, job["study_material_id"])
    resp = await _call(client, who, "GET", f"/study/flashcards/{set_id}")
    assert resp.status_code == 200, resp.text
    data: dict[str, Any] = resp.json()["data"]
    return data


async def set_id_for(client: AsyncClient, who: Actor, material_id: str) -> str:
    from sqlalchemy import select

    from app.models.flashcard import FlashcardSet
    from tests.conftest import _TestSessionLocal

    async with _TestSessionLocal() as db:
        found = (
            await db.execute(
                select(FlashcardSet.id).where(
                    FlashcardSet.study_material_id == uuid.UUID(material_id)
                )
            )
        ).scalar_one()
    return str(found)


class TestSimilarity:
    def test_paraphrase_is_near_duplicate(self) -> None:
        assert similarity("What is overfitting?", "Define overfitting.") == 1.0
        assert find_near_duplicates(
            ["What is gradient descent?", "Define gradient descent", "What is backpropagation?"]
        ) == [1]

    def test_different_cards_are_not_duplicates(self) -> None:
        assert find_near_duplicates(["What is a mitochondrion?", "What is a chloroplast?"]) == []


class TestGeneration:
    async def test_deck_structure_and_references(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        doc, job, deck = await make_deck(client, study, alice, db_session)
        assert deck["card_count"] == 3
        assert [c["display_order"] for c in deck["cards"]] == [0, 1, 2]
        first = deck["cards"][0]
        assert (first["front"], first["back"]) == ("What do chloroplasts capture?", "Light energy.")
        assert first["card_type"] == "basic" and first["origin"] == "generated"
        # the invented source number 99 is stripped; the real one maps to a real chunk
        refs = first["source_references"]
        assert [r["rank"] for r in refs] == [1]
        assert refs[0]["document_id"] == str(doc.id) and refs[0]["chunk_id"]
        # the material keeps the original snapshot as version 1
        mat = (
            await _call(client, alice, "GET", f"/study/materials/{job['study_material_id']}")
        ).json()
        assert mat["data"]["resource_type"] == "flashcards"
        assert len(mat["data"]["content"]["payload"]["cards"]) == 3
        assert "chloroplasts" not in json.dumps(mat["data"]["content"]["sources"])  # ids only

    @pytest.mark.parametrize(
        "card_type",
        ["basic", "definition", "concept", "comparison", "fill_in_the_blank", "application"],
    )
    async def test_every_card_type_is_accepted(
        self,
        client: AsyncClient,
        study: Harness,
        alice: Actor,
        db_session: AsyncSession,
        card_type: str,
    ) -> None:
        front = (
            "Fill the ___ here please." if card_type == "fill_in_the_blank" else "Question about X?"
        )
        _, _, deck = await make_deck(
            client,
            study,
            alice,
            db_session,
            [card(front, "Short answer", card_type=card_type)],
            card_type=card_type,
            count=1,
        )
        assert deck["cards"][0]["card_type"] == card_type

    async def test_prompt_states_settings(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        await make_deck(
            client,
            study,
            alice,
            db_session,
            count=5,
            difficulty="mixed",
            language="French",
            include_explanations=True,
        )
        turn = study.provider.calls[0].messages[0].content
        assert "at most 5 flashcards" in turn and "French" in turn and "<<<SOURCE 1 |" in turn

    async def test_unsupported_cards_are_dropped(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        cards = [
            card("What do chloroplasts capture?", "Light.", source_refs=[1]),
            card("Who won the 1998 final?", "Nobody knows.", source_refs=[77]),
        ]
        _, _, deck = await make_deck(client, study, alice, db_session, cards)
        assert deck["card_count"] == 1

    async def test_references_can_be_turned_off(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        _, _, deck = await make_deck(
            client, study, alice, db_session, include_source_references=False
        )
        assert all(c["source_references"] == [] for c in deck["cards"])

    async def test_explanations_can_be_turned_off(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        _, _, deck = await make_deck(client, study, alice, db_session, include_explanations=False)
        assert all(c["explanation"] is None for c in deck["cards"])

    async def test_card_text_is_stored_as_data_not_markup(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        cards = [card("What does <script>alert(1)</script> do?", "Nothing \x00at all")]
        _, _, deck = await make_deck(client, study, alice, db_session, cards)
        back = deck["cards"][0]["back"]
        assert "\x00" not in back  # control characters stripped
        assert deck["cards"][0]["front"].startswith("What does <script>")  # rendered escaped by UI


class TestQualityRules:
    @pytest.mark.parametrize(
        ("bad", "rule"),
        [
            (card("Define overfitting here.", "define overfitting here."), "identical"),
            (card("Fill in the blank please.", "word", card_type="fill_in_the_blank"), "no blank"),
            (
                card("The ___ is the powerhouse.", "x" * 200, card_type="fill_in_the_blank"),
                "answer too long",
            ),
            (card("Q?", "Short answer."), "front"),  # front under 5 characters
            (card("A" * 500, "Short answer."), "front"),  # front over the cap
        ],
    )
    async def test_invalid_cards_get_one_correction_then_fail(
        self,
        client: AsyncClient,
        study: Harness,
        alice: Actor,
        db_session: AsyncSession,
        bad: dict[str, Any],
        rule: str,
    ) -> None:
        doc = await add_doc(db_session, alice, "Bio", ["Photosynthesis. " + LONG])
        study.provider.reply = reply([bad])
        resp = await _call(
            client,
            alice,
            "POST",
            "/study/generations",
            json={
                "generation_type": "flashcards",
                "source": {"type": "document", "id": str(doc.id)},
            },
        )
        job_id = resp.json()["data"]["id"]
        assert await study.run(job_id) == "failed"
        assert len(study.provider.calls) == 2  # exactly one correction call
        job = await get_job(client, alice, job_id)
        assert job["error_code"] == "GENERATION_INVALID_OUTPUT" and job["study_material_id"] is None

    async def test_near_duplicates_are_rejected(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        doc = await add_doc(db_session, alice, "Bio", ["Photosynthesis. " + LONG])
        dup = [
            card("What is overfitting?", "A model that memorises noise."),
            card("Define overfitting.", "A model memorising noise."),
        ]
        study.provider.replies = [reply(dup)]  # first answer has duplicates
        study.provider.reply = reply([dup[0]])  # the correction is clean
        resp = await _call(
            client,
            alice,
            "POST",
            "/study/generations",
            json={
                "generation_type": "flashcards",
                "source": {"type": "document", "id": str(doc.id)},
            },
        )
        job_id = resp.json()["data"]["id"]
        assert await study.run(job_id) == "completed"
        assert len(study.provider.calls) == 2
        correction = study.provider.calls[1].messages[-1].content
        assert "duplicate" in correction and "overfitting" not in correction

    async def test_more_cards_than_requested_is_invalid(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        doc = await add_doc(db_session, alice, "Bio", ["Photosynthesis. " + LONG])
        study.provider.reply = reply()  # three cards
        resp = await _call(
            client,
            alice,
            "POST",
            "/study/generations",
            json={
                "generation_type": "flashcards",
                "source": {"type": "document", "id": str(doc.id)},
                "settings": {"count": 2},
            },
        )
        assert await study.run(resp.json()["data"]["id"]) == "failed"

    @pytest.mark.parametrize(
        "settings",
        [{"count": 0}, {"count": 51}, {"card_type": "essay"}, {"difficulty": "extreme"}, {"x": 1}],
    )
    async def test_settings_are_validated(
        self,
        client: AsyncClient,
        study: Harness,
        alice: Actor,
        db_session: AsyncSession,
        settings: dict[str, Any],
    ) -> None:
        doc = await add_doc(db_session, alice, "Bio", ["Photosynthesis. " + LONG])
        resp = await _call(
            client,
            alice,
            "POST",
            "/study/generations",
            json={
                "generation_type": "flashcards",
                "source": {"type": "document", "id": str(doc.id)},
                "settings": settings,
            },
        )
        assert resp.status_code == 422

    async def test_daily_quota_applies(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        study.configure(study_daily_generation_quota=1)
        doc = await add_doc(db_session, alice, "Bio", ["Photosynthesis. " + LONG])
        body = {"generation_type": "flashcards", "source": {"type": "document", "id": str(doc.id)}}
        assert (
            await _call(client, alice, "POST", "/study/generations", json=body)
        ).status_code == 202
        body["settings"] = {"count": 5}
        resp = await _call(client, alice, "POST", "/study/generations", json=body)
        assert (resp.status_code, resp.json()["error"]["code"]) == (
            429,
            "GENERATION_QUOTA_EXCEEDED",
        )


class TestEditing:
    async def test_edit_add_delete_favourite(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        _, _, deck = await make_deck(client, study, alice, db_session)
        first = deck["cards"][0]
        patched = await _call(
            client,
            alice,
            "PATCH",
            f"/study/flashcards/cards/{first['id']}",
            json={"front": "What do chloroplasts absorb?", "difficulty": "hard"},
        )
        assert patched.status_code == 200, patched.text
        body = patched.json()["data"]
        assert body["front"] == "What do chloroplasts absorb?" and body["difficulty"] == "hard"
        assert body["revision"] == first["revision"] + 1
        fav = await _call(
            client,
            alice,
            "PATCH",
            f"/study/flashcards/cards/{first['id']}",
            json={"is_favourite": True},
        )
        assert fav.json()["data"]["is_favourite"] is True
        assert fav.json()["data"]["revision"] == body["revision"]  # not a content edit

        added = await _call(
            client,
            alice,
            "POST",
            f"/study/flashcards/{deck['id']}/cards",
            json={"front": "What is ATP used for?", "back": "Energy transfer."},
        )
        assert added.status_code == 201, added.text
        assert added.json()["data"]["origin"] == "manual"
        assert added.json()["data"]["display_order"] == 3
        assert added.json()["data"]["source_references"] == []

        gone = await _call(client, alice, "DELETE", f"/study/flashcards/cards/{first['id']}")
        assert gone.status_code == 204
        again = await _call(client, alice, "DELETE", f"/study/flashcards/cards/{first['id']}")
        assert again.status_code == 404
        reread = (await _call(client, alice, "GET", f"/study/flashcards/{deck['id']}")).json()
        assert reread["data"]["card_count"] == 3

    @pytest.mark.parametrize(
        "body",
        [
            {},
            {"front": None},
            {"front": "x"},
            {"back": ""},
            {"card_type": "essay"},
            {"difficulty": "nope"},
            {"unknown": 1},
            {"front": "Fill the blank here.", "card_type": "fill_in_the_blank"},
        ],
    )
    async def test_invalid_edits_are_rejected(
        self,
        client: AsyncClient,
        study: Harness,
        alice: Actor,
        db_session: AsyncSession,
        body: dict[str, Any],
    ) -> None:
        _, _, deck = await make_deck(client, study, alice, db_session)
        cid = deck["cards"][0]["id"]
        resp = await _call(client, alice, "PATCH", f"/study/flashcards/cards/{cid}", json=body)
        assert resp.status_code == 422, resp.text
        after = (await _call(client, alice, "GET", f"/study/flashcards/{deck['id']}")).json()
        assert after["data"]["cards"][0]["front"] == deck["cards"][0]["front"]

    async def test_duplicate_and_limit_on_manual_cards(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        _, _, deck = await make_deck(client, study, alice, db_session)
        dup = await _call(
            client,
            alice,
            "POST",
            f"/study/flashcards/{deck['id']}/cards",
            json={"front": "What do chloroplasts capture", "back": "Light energy"},
        )
        assert (dup.status_code, dup.json()["error"]["code"]) == (409, "FLASHCARD_DUPLICATE")
        second = deck["cards"][1]
        clash = await _call(
            client,
            alice,
            "PATCH",
            f"/study/flashcards/cards/{second['id']}",
            json={"front": "What do chloroplasts capture?"},
        )
        assert clash.status_code == 409

    async def test_reorder(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        _, _, deck = await make_deck(client, study, alice, db_session)
        ids = [c["id"] for c in deck["cards"]]
        new = [ids[2], ids[0], ids[1]]
        resp = await _call(
            client, alice, "PUT", f"/study/flashcards/{deck['id']}/order", json={"card_ids": new}
        )
        assert resp.status_code == 200
        assert [c["id"] for c in resp.json()["data"]] == new
        assert [c["display_order"] for c in resp.json()["data"]] == [0, 1, 2]
        for bad in ([ids[0]], [ids[0], ids[0], ids[1]], [*ids, str(uuid.uuid4())]):
            r = await _call(
                client,
                alice,
                "PUT",
                f"/study/flashcards/{deck['id']}/order",
                json={"card_ids": bad},
            )
            assert r.status_code == 422, bad

    async def test_generic_material_paths_refuse_decks(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        _, job, _ = await make_deck(client, study, alice, db_session)
        mid = job["study_material_id"]
        for method, url, body in (
            ("PATCH", f"/study/materials/{mid}", {"expected_version": 1, "payload": {}}),
            ("POST", f"/study/materials/{mid}/restore", {"expected_version": 1, "version": 1}),
            ("POST", f"/study/materials/{mid}/regenerate", {}),
        ):
            resp = await _call(client, alice, method, url, json=body)
            assert resp.status_code == 422, (url, resp.text)


async def start_regeneration(
    client: AsyncClient,
    study: Harness,
    who: Actor,
    deck: dict[str, Any],
    ids: list[str],
    cards: list[dict[str, Any]],
) -> str:
    study.provider.reply = reply(cards)
    resp = await _call(
        client, who, "POST", f"/study/flashcards/{deck['id']}/regenerate", json={"card_ids": ids}
    )
    assert resp.status_code == 202, resp.text
    job_id = resp.json()["data"]["id"]
    assert await study.run(job_id) == "completed"
    return str(job_id)


class TestRegenerateSelected:
    async def test_preview_changes_nothing_until_applied(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        _, _, deck = await make_deck(client, study, alice, db_session)
        ids = [deck["cards"][0]["id"], deck["cards"][1]["id"]]
        new = [
            card("Which pigment absorbs light?", "Chlorophyll.", source_refs=[1]),
            card("Where does glycolysis start?", "In the cytoplasm.", source_refs=[2]),
        ]
        job_id = await start_regeneration(client, study, alice, deck, ids, new)
        assert "at most 2 flashcards" in study.provider.calls[-1].messages[0].content

        prev = await _call(client, alice, "GET", f"/study/generations/{job_id}/preview")
        assert prev.status_code == 200
        assert len(prev.json()["data"]["content"]["payload"]["cards"]) == 2
        same = (await _call(client, alice, "GET", f"/study/flashcards/{deck['id']}")).json()["data"]
        assert [c["front"] for c in same["cards"]] == [c["front"] for c in deck["cards"]]

        applied = await _call(
            client, alice, "POST", f"/study/flashcards/{deck['id']}/regenerate/{job_id}/apply"
        )
        assert applied.status_code == 200, applied.text
        cards = applied.json()["data"]
        assert [c["id"] for c in cards] == [c["id"] for c in deck["cards"]]  # in place, same order
        assert cards[0]["front"] == "Which pigment absorbs light?"
        assert cards[2]["front"] == deck["cards"][2]["front"]  # unselected card untouched
        assert cards[0]["revision"] == deck["cards"][0]["revision"] + 1
        again = await _call(
            client, alice, "POST", f"/study/flashcards/{deck['id']}/regenerate/{job_id}/apply"
        )
        assert again.status_code == 409  # a preview applies once

    async def test_user_edits_are_never_overwritten(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        _, _, deck = await make_deck(client, study, alice, db_session)
        target = deck["cards"][0]
        job_id = await start_regeneration(
            client,
            study,
            alice,
            deck,
            [target["id"]],
            [card("Which pigment absorbs light?", "Chlorophyll.")],
        )
        await _call(
            client,
            alice,
            "PATCH",
            f"/study/flashcards/cards/{target['id']}",
            json={"back": "My own wording."},
        )
        stale = await _call(
            client, alice, "POST", f"/study/flashcards/{deck['id']}/regenerate/{job_id}/apply"
        )
        assert (stale.status_code, stale.json()["error"]["code"]) == (409, "PREVIEW_STALE")
        now = (await _call(client, alice, "GET", f"/study/flashcards/{deck['id']}")).json()["data"]
        assert now["cards"][0]["back"] == "My own wording."

    async def test_deleted_selected_card_makes_preview_stale(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        _, _, deck = await make_deck(client, study, alice, db_session)
        target = deck["cards"][1]
        job_id = await start_regeneration(
            client,
            study,
            alice,
            deck,
            [target["id"]],
            [card("Which pigment absorbs?", "Chlorophyll.")],
        )
        await _call(client, alice, "DELETE", f"/study/flashcards/cards/{target['id']}")
        resp = await _call(
            client, alice, "POST", f"/study/flashcards/{deck['id']}/regenerate/{job_id}/apply"
        )
        assert resp.status_code == 409

    async def test_replacement_that_duplicates_a_kept_card_is_skipped(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        _, _, deck = await make_deck(client, study, alice, db_session)
        target = deck["cards"][0]
        job_id = await start_regeneration(
            client,
            study,
            alice,
            deck,
            [target["id"]],
            [card("Define the Krebs cycle?", "Oxidation of acetyl-CoA.", source_refs=[2])],
        )
        resp = await _call(
            client, alice, "POST", f"/study/flashcards/{deck['id']}/regenerate/{job_id}/apply"
        )
        assert resp.status_code == 200
        assert resp.json()["data"][0]["front"] == target["front"]  # original kept

    async def test_discard_and_generic_apply_refuse(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        _, _, deck = await make_deck(client, study, alice, db_session)
        job_id = await start_regeneration(
            client,
            study,
            alice,
            deck,
            [deck["cards"][0]["id"]],
            [card("Which pigment absorbs light?", "Chlorophyll.")],
        )
        generic = await _call(client, alice, "POST", f"/study/generations/{job_id}/preview/apply")
        assert generic.status_code == 409
        gone = await _call(client, alice, "DELETE", f"/study/generations/{job_id}/preview")
        assert gone.status_code == 204
        resp = await _call(
            client, alice, "POST", f"/study/flashcards/{deck['id']}/regenerate/{job_id}/apply"
        )
        assert resp.status_code == 409

    async def test_selection_rules(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        _, _, deck = await make_deck(client, study, alice, db_session)
        url = f"/study/flashcards/{deck['id']}/regenerate"
        assert (await _call(client, alice, "POST", url, json={"card_ids": []})).status_code == 422
        missing = await _call(client, alice, "POST", url, json={"card_ids": [str(uuid.uuid4())]})
        assert missing.status_code == 404
        bad = await _call(
            client,
            alice,
            "POST",
            url,
            json={"card_ids": [deck["cards"][0]["id"]], "settings": {"count": 99}},
        )
        # the server sets count from the selection, but other bad settings are refused
        assert bad.status_code in (202, 200)
        worse = await _call(
            client,
            alice,
            "POST",
            url,
            json={"card_ids": [deck["cards"][1]["id"]], "settings": {"card_type": "essay"}},
        )
        assert worse.status_code == 422


class TestOwnership:
    async def test_another_user_gets_404_everywhere(
        self,
        client: AsyncClient,
        study: Harness,
        alice: Actor,
        bob: Actor,
        db_session: AsyncSession,
    ) -> None:
        _, job, deck = await make_deck(client, study, alice, db_session)
        sid, cid = deck["id"], deck["cards"][0]["id"]
        job_id = await start_regeneration(
            client,
            study,
            alice,
            deck,
            [cid],
            [card("Which pigment absorbs light?", "Chlorophyll.")],
        )
        cardbody = {"front": "What is ATP used for?", "back": "Energy."}
        for method, url, body in (
            ("GET", f"/study/flashcards/{sid}", None),
            ("POST", f"/study/flashcards/{sid}/cards", cardbody),
            ("PATCH", f"/study/flashcards/cards/{cid}", {"front": "Hijacked front text"}),
            ("DELETE", f"/study/flashcards/cards/{cid}", None),
            ("PUT", f"/study/flashcards/{sid}/order", {"card_ids": [cid]}),
            ("POST", f"/study/flashcards/{sid}/regenerate", {"card_ids": [cid]}),
            ("POST", f"/study/flashcards/{sid}/regenerate/{job_id}/apply", None),
        ):
            kwargs = {"json": body} if body is not None else {}
            resp = await _call(client, bob, method, url, **kwargs)
            assert resp.status_code == 404, (method, url, resp.status_code)
        # nothing changed for the owner
        mine = (await _call(client, alice, "GET", f"/study/flashcards/{sid}")).json()["data"]
        assert mine["card_count"] == 3 and mine["cards"][0]["front"] == deck["cards"][0]["front"]

    async def test_a_card_cannot_be_reached_through_another_users_set_or_job(
        self,
        client: AsyncClient,
        study: Harness,
        alice: Actor,
        bob: Actor,
        db_session: AsyncSession,
    ) -> None:
        _, _, adeck = await make_deck(client, study, alice, db_session)
        _, _, bdeck = await make_deck(client, study, bob, db_session)
        # Bob regenerating with Alice's card ids inside his own set: 404
        resp = await _call(
            client,
            bob,
            "POST",
            f"/study/flashcards/{bdeck['id']}/regenerate",
            json={"card_ids": [adeck["cards"][0]["id"]]},
        )
        assert resp.status_code == 404
        # Bob reordering his set with Alice's ids: refused
        resp = await _call(
            client,
            bob,
            "PUT",
            f"/study/flashcards/{bdeck['id']}/order",
            json={"card_ids": [c["id"] for c in adeck["cards"]]},
        )
        assert resp.status_code == 422

    async def test_login_required(self, client: AsyncClient, study: Harness) -> None:
        nil = "00000000-0000-0000-0000-000000000000"
        for method, url in (
            ("GET", f"/api/v1/study/flashcards/{nil}"),
            ("POST", f"/api/v1/study/flashcards/{nil}/cards"),
            ("PATCH", f"/api/v1/study/flashcards/cards/{nil}"),
            ("DELETE", f"/api/v1/study/flashcards/cards/{nil}"),
            ("PUT", f"/api/v1/study/flashcards/{nil}/order"),
            ("POST", f"/api/v1/study/flashcards/{nil}/regenerate"),
        ):
            assert (await client.request(method, url, json={})).status_code in (401, 403)

    async def test_responses_contain_no_source_text(
        self, client: AsyncClient, study: Harness, alice: Actor, db_session: AsyncSession
    ) -> None:
        _, _, deck = await make_deck(client, study, alice, db_session)
        text = json.dumps(deck)
        assert "word word" not in text and "Photosynthesis in chloroplasts." not in text
