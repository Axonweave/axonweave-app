"""Phase 7 M7.12: the whole Research Studio journey on the fake provider (spec section 36).

Each step calls the real API as one user, in order. Papers are analysed with scripted model replies,
so the test needs no key and no network.
"""

from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.knowledge.test_graph_api import node
from tests.research.test_comparisons import DATASET_A, METRIC, RESULT_B, analysed_paper
from tests.research.test_contradictions import DOWN, UP
from tests.research.test_gaps import LIMIT_DATA, LIMIT_DATA_2
from tests.research.test_projects_api import make as make_project
from tests.retrieval.test_search import Actor
from tests.study.conftest import Harness
from tests.test_closeout_users_config import _call


async def call(client: AsyncClient, who: Actor, method: str, path: str, **kw: Any) -> Any:
    resp = await _call(client, who, method, path, **kw)
    assert resp.status_code < 300, (method, path, resp.status_code, resp.text)
    return resp.json()["data"]


async def test_research_studio_journey(
    client: AsyncClient, db_session: AsyncSession, alice: Actor, bob: Actor, lab: Harness
) -> None:
    # 1-3 project, three papers, extraction (scripted provider)
    project = await make_project(client, alice)
    pid = project["id"]
    a = await analysed_paper(
        client, db_session, alice, lab, pid, "Paper A",
        results=[UP], dataset=[DATASET_A], evaluation=[METRIC], limitations=[LIMIT_DATA],
    )  # fmt: skip
    b = await analysed_paper(
        client, db_session, alice, lab, pid, "Paper B",
        results=[DOWN], dataset=[DATASET_A], evaluation=[METRIC], limitations=[LIMIT_DATA_2],
    )  # fmt: skip
    c = await analysed_paper(client, db_session, alice, lab, pid, "Paper C", results=[RESULT_B])
    papers = await call(client, alice, "GET", f"/research/projects/{pid}/papers")
    assert {p["analysis_status"] for p in papers} == {"analysed"} and len(papers) == 3

    # 4 metadata review
    meta = {"authors": ["Smith, John"], "publication_year": 2020, "venue": "J. Bio"}
    edited = await call(client, alice, "PATCH", f"/research/papers/{a}", json=meta)
    assert edited["publication_year"] == 2020

    # 5-6 structured analysis with evidence
    analysis = await call(client, alice, "GET", f"/research/papers/{a}/analysis")
    assert analysis["sections"], "the analysis has sections"

    # 7 comparison
    cmp_ = await call(
        client, alice, "POST", f"/research/projects/{pid}/comparisons",
        json={"title": "A vs B vs C", "paper_ids": [a, b, c]},
    )  # fmt: skip
    assert cmp_["result"]["rows"]

    # 8 evidence matrix
    matrix = await call(
        client, alice, "POST", f"/research/projects/{pid}/matrices",
        json={"title": "Review", "paper_ids": [a, b, c]},
    )  # fmt: skip
    assert matrix["id"]

    # 9-10 gaps with supporting evidence
    gaps = await call(client, alice, "POST", f"/research/projects/{pid}/gaps/generate", json={})
    assert gaps and all(g["evidence"] for g in gaps)
    reviewed = await call(
        client, alice, "PATCH", f"/research/gaps/{gaps[0]['id']}",
        json={"validation_status": "accepted"},
    )  # fmt: skip
    assert reviewed["validation_status"] == "accepted"

    # 11 contradictions
    found = await call(
        client, alice, "POST", f"/research/projects/{pid}/contradictions/generate", json={}
    )
    assert found

    # 12 citations
    cites = await call(
        client, alice, "POST", f"/research/projects/{pid}/citations",
        json={"style": "apa", "paper_ids": [a]},
    )  # fmt: skip
    assert cites[0]["formatted_citation"] and cites[0]["in_text_citation"]

    # 13-14 literature review draft with a citation marker
    content = f"## Review\n\nLight conversion improves energy yield {{{{cite:{a}}}}}."
    draft = await call(
        client, alice, "POST", f"/research/projects/{pid}/drafts",
        json={"title": "Lit review", "document_type": "literature_review", "content": content},
    )  # fmt: skip
    url = f"/research/drafts/{draft['id']}"

    # 15 claims are validated against paper evidence
    report = await call(client, alice, "POST", f"{url}/check")
    assert report["summary"]["unsupported"] == 0 and report["invalid_references"] == []

    # 16-17 new version, then restore the first
    saved = await call(
        client, alice, "PATCH", url, json={"content": "Changed.", "expected_version": 1}
    )
    assert saved["version_number"] == 2
    restored = await call(
        client, alice, "POST", f"{url}/versions/1/restore", json={"expected_version": 2}
    )
    assert restored["content"] == content and restored["version_number"] == 3

    # 18 knowledge graph concepts
    await node(client, alice, "Light conversion")
    links = await call(
        client, alice, "POST", f"/research/projects/{pid}/concept-links/suggest", json={}
    )
    assert isinstance(links, list)

    # 19 export
    exported = await call(client, alice, "GET", f"{url}/export")
    assert "## References" in exported["content"] and "(Smith, 2020)" in exported["content"]

    # dashboard reflects the work, and none of it is visible to another user
    counts = (await call(client, alice, "GET", "/research/dashboard"))["counts"]
    assert counts["papers"] == 3 and counts["papers_analysed"] == 3
    assert (
        counts["comparisons"] == 1 and counts["matrices"] == 1 and counts["drafts_in_progress"] == 1
    )
    assert (await call(client, bob, "GET", "/research/dashboard"))["counts"]["papers"] == 0
    for path in (url, f"{url}/export", f"/research/projects/{pid}/dashboard"):
        assert (await _call(client, bob, "GET", path)).status_code == 404

    # deleting the project removes everything attached to it
    await _call(client, alice, "DELETE", f"/research/projects/{pid}")
    assert (await _call(client, alice, "GET", url)).status_code == 404
    assert (await _call(client, alice, "GET", f"/research/papers/{a}")).status_code == 404
