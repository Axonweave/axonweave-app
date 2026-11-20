"""Wikipedia as a web source (D-145): the fetcher on a mocked transport (no network) and the way a
web run chooses between the provider's search and Wikipedia. FakeProvider only."""

from typing import Any

import httpx
import pytest
from httpx import AsyncClient

from app.ai.errors import LLMWebSearchUnavailableError
from app.ai.prompts.registry import active_prompt
from app.ai.types import WebSource
from app.knowledge import web_extraction
from app.knowledge.schemas import MAX_CONCEPTS_PER_CALL, ExtractionOutput
from app.knowledge.web_extraction import WebRun, batch_units
from app.knowledge.wikipedia_source import (
    MAX_PAGE_CHARS,
    WikipediaUnavailableError,
    fetch_wikipedia_sources,
    page_url,
    related_titles,
    split_sections,
)
from app.study.source_reader import SourceUnit
from tests.knowledge.test_web_graph import GOOD, SITE_A, SITE_B, execute, job_row, start_web
from tests.retrieval.test_search import Actor
from tests.study.conftest import Harness
from tests.test_closeout_users_config import _call

LEAD = "Mitochondria are organelles that make ATP by cellular respiration. " * 4
ARTICLES = {
    "Mitochondrion": f"{LEAD}\n\n== Structure ==\nAn outer and an inner membrane.\n\n"
    "== References ==\nSmith 2001.",
    "Mitochondria (disambiguation)": "Mitochondria may refer to: " + "x" * 300,
    "Stub": "Short.",
    "ATP": "ATP is the energy currency of the cell and powers many reactions. " * 5,
}


def wiki_transport(seen: list[httpx.Request] | None = None) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        params = request.url.params
        if params.get("list") == "search":
            hits = [{"title": t} for t in ARTICLES]
            return httpx.Response(200, json={"query": {"search": hits}})
        title = params["titles"]
        page = {"title": title, "extract": ARTICLES.get(title, "")}
        return httpx.Response(200, json={"query": {"pages": [page]}})

    return httpx.MockTransport(handler)


class TestSplitSections:
    def test_drops_reference_sections_and_keeps_the_lead(self) -> None:
        parts = split_sections(ARTICLES["Mitochondrion"])
        assert parts[0].startswith("Mitochondria are organelles")
        assert any(p.startswith("Structure") for p in parts)
        assert not any("Smith 2001" in p for p in parts)

    def test_is_capped(self) -> None:
        text = "Lead.\n" + "\n".join(f"== S{i} ==\n{'word ' * 400}" for i in range(30))
        assert sum(len(p) for p in split_sections(text)) <= MAX_PAGE_CHARS


class TestFetch:
    async def test_a_429_is_retried_once_after_the_delay(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        waits: list[float] = []

        async def no_sleep(seconds: float) -> None:
            waits.append(seconds)

        monkeypatch.setattr("app.knowledge.wikipedia_source.asyncio.sleep", no_sleep)
        calls = {"n": 0}
        inner = wiki_transport()

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(429, headers={"retry-after": "2"})
            return inner.handler(request)  # type: ignore[attr-defined]

        out = await fetch_wikipedia_sources(
            "cells", 1, transport=httpx.MockTransport(handler), request_gap=0
        )
        assert len(out) == 1 and 2.0 in waits

    async def test_a_page_that_keeps_failing_keeps_the_earlier_articles(self) -> None:
        inner = wiki_transport()

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.params.get("titles") == "ATP":
                return httpx.Response(500)
            return inner.handler(request)  # type: ignore[attr-defined]

        out = await fetch_wikipedia_sources(
            "cells", 4, transport=httpx.MockTransport(handler), request_gap=0
        )
        assert [s.title for s in out] == ["Mitochondrion - Wikipedia"]

    def test_page_url_is_encoded_and_on_the_fixed_host(self) -> None:
        url = page_url("C++ (language)/x?y=1#z")
        assert url.startswith("https://en.wikipedia.org/wiki/")
        assert "?" not in url and "#" not in url and " " not in url

    async def test_returns_articles_and_skips_stubs_and_disambiguation(self) -> None:
        seen: list[httpx.Request] = []
        out = await fetch_wikipedia_sources(
            "cells", 4, transport=wiki_transport(seen), request_gap=0
        )
        assert [s.title for s in out] == ["Mitochondrion - Wikipedia", "ATP - Wikipedia"]
        assert out[0].url == "https://en.wikipedia.org/wiki/Mitochondrion"
        assert all(r.url.host == "en.wikipedia.org" and r.url.scheme == "https" for r in seen)
        assert seen[0].url.params["srsearch"] == "cells"

    async def test_respects_the_page_cap(self) -> None:
        out = await fetch_wikipedia_sources("cells", 1, transport=wiki_transport(), request_gap=0)
        assert len(out) == 1

    async def test_a_blank_topic_fetches_nothing(self) -> None:
        seen: list[httpx.Request] = []
        assert (
            await fetch_wikipedia_sources("   ", 3, transport=wiki_transport(seen), request_gap=0)
            == ()
        )
        assert seen == []

    async def test_an_error_status_is_unavailable(self) -> None:
        transport = httpx.MockTransport(lambda r: httpx.Response(503))
        with pytest.raises(WikipediaUnavailableError):
            await fetch_wikipedia_sources("cells", 3, transport=transport, request_gap=0)

    async def test_an_oversized_response_is_unavailable(self) -> None:
        transport = httpx.MockTransport(lambda r: httpx.Response(200, content=b"x" * 3_000_000))
        with pytest.raises(WikipediaUnavailableError):
            await fetch_wikipedia_sources("cells", 3, transport=transport, request_gap=0)

    async def test_a_network_failure_is_unavailable(self) -> None:
        def boom(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("down")

        with pytest.raises(WikipediaUnavailableError):
            await fetch_wikipedia_sources(
                "cells", 3, transport=httpx.MockTransport(boom), request_gap=0
            )


WIKI_A = WebSource(
    "https://en.wikipedia.org/wiki/Mitochondrion", "Mitochondrion - Wikipedia", SITE_A.segments
)
WIKI_B = WebSource("https://en.wikipedia.org/wiki/ATP", "ATP - Wikipedia", SITE_B.segments)


def use_mode(lab: Harness, monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    monkeypatch.setattr(lab.runtime.settings, "knowledge_web_source", mode)


def search_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    async def refuse(self: Any, cfg: Any, catalog: Any, topic: str) -> Any:
        raise LLMWebSearchUnavailableError

    monkeypatch.setattr(WebRun, "_search_sources", refuse)


def wikipedia_returns(monkeypatch: pytest.MonkeyPatch, result: Any) -> list[str]:
    topics: list[str] = []

    async def fake(topic: str, max_pages: int, **kw: Any) -> Any:
        topics.append(topic)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(web_extraction, "fetch_wikipedia_sources", fake)
    return topics


async def queue(client: AsyncClient, who: Actor, lab: Harness) -> str:
    lab.provider.reply = GOOD
    resp = await start_web(client, who)
    assert resp.status_code == 202, resp.text
    return str(resp.json()["data"]["id"])


class TestChoosingTheSource:
    async def test_auto_falls_back_to_wikipedia_when_search_is_unavailable(
        self, client: AsyncClient, alice: Actor, lab: Harness, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        use_mode(lab, monkeypatch, "auto")
        search_unavailable(monkeypatch)
        topics = wikipedia_returns(monkeypatch, (WIKI_A, WIKI_B))
        job_id = await queue(client, alice, lab)
        assert await execute(lab, job_id) == "completed"
        assert topics == [alice.subject.name]
        job = await job_row(job_id)
        assert (job.result_stats or {})["nodes_created"] == 2

    async def test_the_saved_evidence_links_to_the_article(
        self, client: AsyncClient, alice: Actor, lab: Harness, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        use_mode(lab, monkeypatch, "wikipedia")
        wikipedia_returns(monkeypatch, (WIKI_A, WIKI_B))
        assert await execute(lab, await queue(client, alice, lab)) == "completed"
        nodes = (await _call(client, alice, "GET", "/knowledge/nodes?limit=100")).json()["data"]
        mito = next(n for n in nodes if n["name"] == "Mitochondria")
        evidence = (
            await _call(client, alice, "GET", f"/knowledge/nodes/{mito['id']}/evidence")
        ).json()["data"]
        assert [(e["source_kind"], e["source_url"], e["source_title"]) for e in evidence] == [
            ("web", WIKI_A.url, WIKI_A.title)
        ]

    async def test_search_only_mode_does_not_fall_back(
        self, client: AsyncClient, alice: Actor, lab: Harness, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        use_mode(lab, monkeypatch, "gemini_search")
        search_unavailable(monkeypatch)
        topics = wikipedia_returns(monkeypatch, (WIKI_A,))
        job_id = await queue(client, alice, lab)
        assert await execute(lab, job_id) == "failed"
        assert (await job_row(job_id)).error_code == "LLM_WEB_SEARCH_UNAVAILABLE"
        assert topics == []

    async def test_wikipedia_mode_never_calls_the_provider_search(
        self, client: AsyncClient, alice: Actor, lab: Harness, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        use_mode(lab, monkeypatch, "wikipedia")

        async def forbidden(self: Any, cfg: Any, catalog: Any, topic: str) -> Any:
            raise AssertionError("the provider search must not run")

        monkeypatch.setattr(WebRun, "_search_sources", forbidden)
        wikipedia_returns(monkeypatch, (WIKI_A, WIKI_B))
        job_id = await queue(client, alice, lab)
        assert await execute(lab, job_id) == "completed"

    async def test_an_unreachable_wikipedia_fails_with_no_sources(
        self, client: AsyncClient, alice: Actor, lab: Harness, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        use_mode(lab, monkeypatch, "wikipedia")
        wikipedia_returns(monkeypatch, WikipediaUnavailableError())
        job_id = await queue(client, alice, lab)
        assert await execute(lab, job_id) == "failed"
        assert (await job_row(job_id)).error_code == "KNOWLEDGE_NO_WEB_SOURCES"

    async def test_no_matching_articles_fails_with_no_sources(
        self, client: AsyncClient, alice: Actor, lab: Harness, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        use_mode(lab, monkeypatch, "wikipedia")
        wikipedia_returns(monkeypatch, ())
        job_id = await queue(client, alice, lab)
        assert await execute(lab, job_id) == "failed"
        assert (await job_row(job_id)).error_code == "KNOWLEDGE_NO_WEB_SOURCES"


def unit(index: int, tokens: int) -> SourceUnit:
    return SourceUnit(
        chunk_id=None,
        document_id=None,
        document_name=f"page {index}",
        chunk_index=index,
        content="x",
        page_number=None,
        slide_number=None,
        section_heading=None,
        tokens=tokens,
    )


class TestBatchUnits:
    def test_groups_in_order_up_to_the_batch_size(self) -> None:
        units = [unit(i, 400) for i in range(5)]
        groups = batch_units(units, per_batch=1000, unit_limit=5000, max_batches=10)
        assert [[u.chunk_index for u in g] for g in groups] == [[0, 1], [2, 3], [4]]

    def test_a_big_passage_gets_its_own_batch_and_an_oversized_one_is_skipped(self) -> None:
        units = [unit(0, 300), unit(1, 2000), unit(2, 9000), unit(3, 300)]
        groups = batch_units(units, per_batch=1000, unit_limit=5000, max_batches=10)
        assert [[u.chunk_index for u in g] for g in groups] == [[0], [1], [3]]

    def test_the_number_of_batches_is_capped(self) -> None:
        units = [unit(i, 900) for i in range(6)]
        assert len(batch_units(units, per_batch=1000, unit_limit=5000, max_batches=3)) == 3

    def test_nothing_in_nothing_out(self) -> None:
        assert batch_units([], 1000, 5000, 5) == []


class TestThoroughExtraction:
    def test_the_active_prompt_asks_for_thorough_connected_extraction(self) -> None:
        prompt = active_prompt("knowledge_extract")
        assert prompt.version == 2
        assert "Be thorough" in prompt.content and "connected graph" in prompt.content
        assert "fewer" not in prompt.content  # v1 told the model to prefer fewer items
        assert "EXACTLY" in prompt.content  # the grounding rules are kept

    async def test_a_web_run_extracts_in_several_batches(
        self, client: AsyncClient, alice: Actor, lab: Harness, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        use_mode(lab, monkeypatch, "wikipedia")
        monkeypatch.setattr(lab.runtime.settings, "knowledge_web_batch_tokens", 20)
        wikipedia_returns(monkeypatch, (WIKI_A, WIKI_B))
        job_id = await queue(client, alice, lab)
        assert await execute(lab, job_id) == "completed"
        stats = (await job_row(job_id)).source_stats or {}
        assert stats["web_sources"] == 2 and stats["batches"] == 2


def raw_concept(**kw: Any) -> dict[str, Any]:
    return {"name": "Chloroplast", "evidence": [{"source": 1, "quote": "abc"}], **kw}


class TestLenientOutput:
    def test_an_unknown_label_becomes_the_generic_one(self) -> None:
        out = ExtractionOutput.model_validate(
            {
                "concepts": [raw_concept(type="organelle", difficulty="hard")],
                "relationships": [
                    {
                        "source": "aa",
                        "target": "bb",
                        "type": "is located inside",
                        "evidence": [{"source": 1, "quote": "abc"}],
                    }
                ],
            }
        )
        assert out.concepts[0].type == "concept" and out.concepts[0].difficulty is None
        assert out.relationships[0].type == "RELATED_TO"

    def test_known_labels_are_kept(self) -> None:
        out = ExtractionOutput.model_validate(
            {"concepts": [raw_concept(type="Algorithm", difficulty="advanced")]}
        )
        assert out.concepts[0].type == "algorithm" and out.concepts[0].difficulty == "advanced"

    def test_too_many_items_are_trimmed_not_rejected(self) -> None:
        out = ExtractionOutput.model_validate(
            {"concepts": [raw_concept() for _ in range(MAX_CONCEPTS_PER_CALL + 40)]}
        )
        assert len(out.concepts) == MAX_CONCEPTS_PER_CALL


class TestRelatedTitles:
    def test_drops_off_topic_hits_and_disambiguation_pages(self) -> None:
        titles = [
            "Photosynthesis",
            "Food",
            "Photosynthesis (disambiguation)",
            "Artificial photosynthesis",
        ]
        assert related_titles("Photosynthesis", titles) == [
            "Photosynthesis",
            "Artificial photosynthesis",
        ]

    def test_matches_word_forms(self) -> None:
        titles = ["Systems design", "Design system", "Banana"]
        assert related_titles("System design", titles) == ["Systems design", "Design system"]

    def test_falls_back_to_the_search_order_when_nothing_matches(self) -> None:
        assert related_titles("Thermodynamics", ["Heat", "Entropy"]) == ["Heat", "Entropy"]
