"""SourceReader: ordered, sampled and batched reads (D-79)."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.study_source_repository import StudySourceRepository
from app.study.errors import NoSourcesError, SourceTooLargeError
from app.study.schemas import SourceSpec
from app.study.source_reader import SourceReader, pick_evenly
from tests.ai.test_provider_layer import make_settings
from tests.retrieval.test_search import Actor, add_doc


@pytest.fixture
async def alice(db_session: AsyncSession) -> Actor:
    from tests.retrieval.test_search import actor

    return await actor(db_session, "alice-reader@example.com")


@pytest.fixture
async def bob(db_session: AsyncSession) -> Actor:
    from tests.retrieval.test_search import actor

    return await actor(db_session, "bob-reader@example.com")


class TestPickEvenly:
    def test_everything_fits(self) -> None:
        assert pick_evenly([10, 10, 10], 100) == [0, 1, 2]

    def test_spreads_across_the_whole_range(self) -> None:
        chosen = pick_evenly([100] * 50, 1000)
        assert len(chosen) == 10
        assert chosen[0] == 0 and chosen[-1] >= 40  # the end of the scope is represented
        assert chosen == sorted(set(chosen))
        gaps = {b - a for a, b in zip(chosen, chosen[1:], strict=False)}
        assert gaps == {5}

    def test_never_exceeds_the_budget_and_handles_edges(self) -> None:
        sizes = [300, 10, 500, 20, 40, 700, 5]
        chosen = pick_evenly(sizes, 600)
        assert sum(sizes[i] for i in chosen) <= 600
        assert pick_evenly([], 100) == [] and pick_evenly([5], 0) == []

    def test_one_huge_item_still_yields_a_valid_pick(self) -> None:
        assert pick_evenly([5000, 5000], 100) == [0]  # first is always taken, never an empty prompt


class TestReader:
    async def test_ordered_read_is_in_reading_order_and_complete(
        self, db_session: AsyncSession, alice: Actor
    ) -> None:
        await add_doc(db_session, alice, "B doc", ["b0", "b1"])
        await add_doc(db_session, alice, "A doc", ["a0", "a1", "a2"])
        reader = SourceReader(db_session, make_settings())
        source = await reader.resolve(
            alice.user.id, SourceSpec(type="subject", id=alice.subject.id)
        )
        estimate = await reader.estimate(source)
        assert (estimate.units, estimate.documents) == (5, 2)
        bundle = await reader.read_ordered(source, 10_000)
        assert [u.content for u in bundle.units] == ["a0", "a1", "a2", "b0", "b1"]
        assert bundle.mode == "ordered" and not bundle.truncated

    async def test_ordered_refuses_instead_of_silently_cutting(
        self, db_session: AsyncSession, alice: Actor
    ) -> None:
        await add_doc(db_session, alice, "Doc", ["x" * 400] * 5)
        reader = SourceReader(db_session, make_settings())
        source = await reader.resolve(alice.user.id, SourceSpec(type="workspace", id=alice.ws.id))
        with pytest.raises(SourceTooLargeError):
            await reader.read_ordered(source, 50)

    async def test_batches_cover_every_chunk_exactly_once(
        self, db_session: AsyncSession, alice: Actor
    ) -> None:
        await add_doc(db_session, alice, "Doc 1", [f"one-{i} " + "w" * 200 for i in range(7)])
        await add_doc(db_session, alice, "Doc 2", [f"two-{i} " + "w" * 200 for i in range(6)])
        reader = SourceReader(db_session, make_settings())
        source = await reader.resolve(
            alice.user.id, SourceSpec(type="subject", id=alice.subject.id)
        )
        whole = await reader.read_ordered(source, 100_000)
        batches = await reader.ordered_batches(source, 120)
        assert len(batches) > 1
        flat = [u.chunk_id for b in batches for u in b.units]
        assert flat == [u.chunk_id for u in whole.units]  # same order, none skipped, none repeated
        assert len(set(flat)) == 13
        assert all(b.tokens <= 120 or len(b.units) == 1 for b in batches)

    async def test_sampled_covers_start_middle_and_end(
        self, db_session: AsyncSession, alice: Actor
    ) -> None:
        await add_doc(db_session, alice, "Doc", [f"chunk-{i:02d} " + "w" * 100 for i in range(30)])
        reader = SourceReader(db_session, make_settings())
        source = await reader.resolve(alice.user.id, SourceSpec(type="workspace", id=alice.ws.id))
        bundle = await reader.read_sampled(source, 300)
        indexes = [u.chunk_index for u in bundle.units]
        assert bundle.truncated and bundle.mode == "sampled"
        assert indexes[0] == 0 and indexes[-1] >= 20 and indexes == sorted(indexes)

    async def test_retrieved_returns_relevant_chunks_in_reading_order(
        self, db_session: AsyncSession, alice: Actor
    ) -> None:
        await add_doc(
            db_session,
            alice,
            "Doc",
            ["Roman emperors ruled", "Photosynthesis in chloroplasts", "Krebs cycle steps"],
        )
        reader = SourceReader(db_session, make_settings())
        source = await reader.resolve(alice.user.id, SourceSpec(type="workspace", id=alice.ws.id))
        bundle = await reader.read_retrieved(source, "photosynthesis chloroplasts", 1000, top_k=1)
        assert bundle.mode == "retrieved"
        assert [u.content for u in bundle.units] == ["Photosynthesis in chloroplasts"]

    async def test_other_users_chunks_are_unreachable(
        self, db_session: AsyncSession, alice: Actor, bob: Actor
    ) -> None:
        doc = await add_doc(db_session, alice, "Alice only", ["secret"])
        repo = StudySourceRepository(db_session)
        index = await repo.chunk_index(alice.user.id, [doc.id], 1)
        assert len(index) == 1
        # Bob asking for Alice's document or chunk ids gets nothing.
        assert await repo.chunk_index(bob.user.id, [doc.id], 1) == []
        assert await repo.chunks_by_ids(bob.user.id, [doc.id], [index[0][0]], 1) == []
        assert await repo.placements(bob.user.id, [doc.id]) == []

    async def test_unready_and_empty_scopes(self, db_session: AsyncSession, alice: Actor) -> None:
        await add_doc(db_session, alice, "Not ready", ["x"], status="queued")
        await add_doc(db_session, alice, "Archived", ["x"], archived=True)
        reader = SourceReader(db_session, make_settings())
        with pytest.raises(NoSourcesError):
            await reader.resolve(alice.user.id, SourceSpec(type="subject", id=alice.subject.id))

    async def test_text_source_and_size_limit(self, db_session: AsyncSession, alice: Actor) -> None:
        reader = SourceReader(db_session, make_settings(study_max_text_source_chars=100))
        spec = SourceSpec(type="text", text="short note", workspace_id=alice.ws.id)
        source = await reader.resolve(alice.user.id, spec)
        bundle = await reader.read_ordered(source, 1000)
        assert bundle.mode == "text" and bundle.units[0].chunk_id is None
        big = SourceSpec(type="text", text="x" * 101, workspace_id=alice.ws.id)
        with pytest.raises(SourceTooLargeError):
            await reader.resolve(alice.user.id, big)
        with pytest.raises(Exception) as err:  # foreign workspace is a 404
            await reader.resolve(uuid.uuid4(), spec)
        assert getattr(err.value, "status_code", None) == 404

    async def test_too_many_documents_is_refused(
        self, db_session: AsyncSession, alice: Actor
    ) -> None:
        for i in range(3):
            await add_doc(db_session, alice, f"Doc {i}", ["x"])
        reader = SourceReader(db_session, make_settings(study_max_sources_per_request=2))
        with pytest.raises(SourceTooLargeError):
            await reader.resolve(alice.user.id, SourceSpec(type="subject", id=alice.subject.id))
