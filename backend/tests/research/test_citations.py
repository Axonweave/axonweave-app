"""Phase 7 M7.8: citations (five styles, validation, regeneration, bibliography, access)."""

from datetime import date
from typing import Any

from httpx import AsyncClient

from app.research.citations import Meta, format_citation, in_text, validate
from tests.research.test_projects_api import make as make_project
from tests.retrieval.test_search import Actor
from tests.test_closeout_users_config import _call

FULL = Meta(
    authors=("Smith, John A.", "Jane Doe", "Lee, Min"),
    title="Deep learning for cells",
    year=2020,
    venue="Journal of Biology",
    volume="12",
    issue="3",
    pages="45-67",
    doi="10.1000/abc123",
    verified=True,
)


class TestFormats:
    def test_apa(self) -> None:
        assert format_citation("apa", FULL) == (
            "Smith, J. A., Doe, J., & Lee, M. (2020). Deep learning for cells. "
            "Journal of Biology, 12(3), 45–67. https://doi.org/10.1000/abc123"
        )

    def test_ieee(self) -> None:
        assert format_citation("ieee", FULL) == (
            "J. A. Smith, J. Doe, and M. Lee, “Deep learning for cells,” "
            "Journal of Biology, vol. 12, no. 3, pp. 45–67, 2020, doi: 10.1000/abc123."
        )

    def test_mla(self) -> None:
        assert format_citation("mla", FULL) == (
            "Smith, John A., et al. “Deep learning for cells.” Journal of Biology, "
            "vol. 12, no. 3, 2020, pp. 45–67. https://doi.org/10.1000/abc123."
        )

    def test_chicago(self) -> None:
        assert format_citation("chicago", FULL) == (
            "Smith, John A., Jane Doe, and Min Lee. 2020. “Deep learning for cells.” "
            "Journal of Biology 12 (3): 45–67. https://doi.org/10.1000/abc123."
        )

    def test_harvard(self) -> None:
        assert format_citation("harvard", FULL) == (
            "Smith, J.A., Doe, J. and Lee, M. (2020) ‘Deep learning for cells’, "
            "Journal of Biology, 12(3), pp. 45–67. doi:10.1000/abc123."
        )

    def test_in_text_forms(self) -> None:
        two = Meta(authors=("Smith, John", "Doe, Jane"), title="T", year=2021)
        assert in_text("apa", FULL) == "(Smith et al., 2020)"
        assert in_text("apa", two) == "(Smith & Doe, 2021)"
        assert in_text("harvard", two) == "(Smith and Doe, 2021)"
        assert in_text("chicago", FULL) == "(Smith et al. 2020)"
        assert in_text("mla", FULL) == "(Smith et al.)"
        assert in_text("ieee", FULL, 3) == "[3]"

    def test_missing_details_are_left_out_never_invented(self) -> None:
        bare = Meta(authors=(), title="An untitled-venue study")
        apa = format_citation("apa", bare)
        assert apa == "An untitled-venue study. (n.d.)."
        for style in ("ieee", "mla", "chicago", "harvard"):
            text = format_citation(style, bare)
            assert "An untitled-venue study" in text
            assert "None" not in text and "Unknown" not in text
        assert in_text("apa", bare) == "(“An untitled-venue study”, n.d.)"


class TestValidation:
    def codes(self, meta: Meta) -> set[str]:
        return {i.code for i in validate(meta, today=date(2026, 1, 1))}

    def test_complete_metadata_has_no_blocking_issue(self) -> None:
        issues = validate(FULL, today=date(2026, 1, 1))
        assert not [i for i in issues if i.severity in ("missing", "warning")]

    def test_missing_fields_are_named(self) -> None:
        codes = self.codes(Meta(authors=(), title="Ok title"))
        assert {"MISSING_AUTHORS", "MISSING_YEAR", "MISSING_VENUE", "UNVERIFIED_METADATA"} <= codes

    def test_bad_values_are_flagged(self) -> None:
        meta = Meta(
            authors=("Smith, John", "Smith, John", "Plato"),
            title="Valid title",
            year=2090,
            venue="V",
            doi="not-a-doi",
            pages="67-45",
        )
        codes = self.codes(meta)
        assert {"DUPLICATE_AUTHOR", "INCOMPLETE_AUTHOR", "INVALID_YEAR", "INVALID_DOI"} <= codes
        assert "INVALID_PAGES" in codes


async def paper(client: AsyncClient, who: Actor, pid: str, **kw: Any) -> str:
    body: dict[str, Any] = {
        "title": "Deep learning for cells",
        "authors": ["Smith, John A.", "Jane Doe", "Lee, Min"],
        "publication_year": 2020,
        "venue": "Journal of Biology",
        "volume": "12",
        "issue": "3",
        "pages": "45-67",
        "doi": "10.1000/abc123",
        **kw,
    }
    resp = await _call(client, who, "POST", f"/research/projects/{pid}/papers", json=body)
    assert resp.status_code == 201, resp.text
    made: str = resp.json()["data"]["id"]
    return made


class TestApi:
    async def test_generate_in_each_style_and_validate(
        self, client: AsyncClient, alice: Actor
    ) -> None:
        project = await make_project(client, alice)
        pid = project["id"]
        paper_id = await paper(client, alice, pid)
        for style in ("apa", "ieee", "mla", "chicago", "harvard"):
            resp = await _call(
                client,
                alice,
                "POST",
                f"/research/projects/{pid}/citations",
                json={"style": style, "paper_ids": [paper_id]},
            )
            assert resp.status_code == 200, resp.text
            row = resp.json()["data"][0]
            assert row["citation_style"] == style
            assert row["formatted_citation"] == format_citation(style, FULL)
            assert row["metadata_changed"] is False
        apa = (
            await _call(client, alice, "GET", f"/research/projects/{pid}/citations?style=apa")
        ).json()
        assert apa["total"] == 1 and apa["data"][0]["in_text_citation"] == "(Smith et al., 2020)"
        # unverified metadata is reported, not hidden
        assert "UNVERIFIED_METADATA" in {i["code"] for i in apa["data"][0]["issues"]}

    async def test_missing_metadata_is_reported_and_not_invented(
        self, client: AsyncClient, alice: Actor
    ) -> None:
        project = await make_project(client, alice)
        pid = project["id"]
        bare = await _call(
            client, alice, "POST", f"/research/projects/{pid}/papers", json={"title": "Bare paper"}
        )
        resp = await _call(
            client,
            alice,
            "POST",
            f"/research/projects/{pid}/citations",
            json={"style": "apa", "paper_ids": [bare.json()["data"]["id"]]},
        )
        row = resp.json()["data"][0]
        assert row["complete"] is False
        assert {"MISSING_AUTHORS", "MISSING_YEAR", "MISSING_VENUE"} <= {
            i["code"] for i in row["issues"]
        }
        assert row["formatted_citation"] == "Bare paper. (n.d.)."

    async def test_changed_metadata_is_detected_and_regenerated(
        self, client: AsyncClient, alice: Actor
    ) -> None:
        project = await make_project(client, alice)
        pid = project["id"]
        paper_id = await paper(client, alice, pid)
        url = f"/research/projects/{pid}/citations"
        body = {"style": "apa", "paper_ids": [paper_id]}
        first = (await _call(client, alice, "POST", url, json=body)).json()["data"][0]
        edit = await _call(
            client, alice, "PATCH", f"/research/papers/{paper_id}", json={"publication_year": 2021}
        )
        assert edit.status_code == 200, edit.text
        stale = (await _call(client, alice, "GET", url)).json()["data"][0]
        assert stale["metadata_changed"] is True and "(2020)" in stale["formatted_citation"]
        again = (await _call(client, alice, "POST", url, json=body)).json()["data"][0]
        assert again["id"] == first["id"]  # refreshed in place, not duplicated
        assert again["metadata_changed"] is False and "(2021)" in again["formatted_citation"]
        assert (await _call(client, alice, "GET", url)).json()["total"] == 1

    async def test_bibliography_export_text_and_bibtex(
        self, client: AsyncClient, alice: Actor
    ) -> None:
        project = await make_project(client, alice)
        pid = project["id"]
        a = await paper(client, alice, pid)
        b = await paper(
            client,
            alice,
            pid,
            title="Another study",
            authors=["Adams, Ann"],
            doi="10.1000/zzz",
            publication_year=2019,
        )
        url = f"/research/projects/{pid}/citations"
        await _call(client, alice, "POST", url, json={"style": "ieee"})
        text = (await _call(client, alice, "GET", f"{url}/bibliography?style=ieee")).json()["data"]
        assert text["count"] == 2 and text["filename"] == "bibliography-ieee.txt"
        lines = text["content"].split("\n\n")
        assert lines[0].startswith("[1] A. Adams") and lines[1].startswith("[2] J. A. Smith")
        await _call(client, alice, "POST", url, json={"style": "apa", "paper_ids": [a, b]})
        bib = (
            await _call(client, alice, "GET", f"{url}/bibliography?style=apa&format=bibtex")
        ).json()["data"]
        assert bib["filename"] == "bibliography.bib" and bib["content"].count("@article{") == 2
        assert "doi = {10.1000/abc123}" in bib["content"] and "adams2019" in bib["content"]

    async def test_validation_and_paper_ownership(self, client: AsyncClient, alice: Actor) -> None:
        project = await make_project(client, alice)
        other = await make_project(client, alice)
        stray = await paper(client, alice, other["id"])
        url = f"/research/projects/{project['id']}/citations"
        assert (await _call(client, alice, "POST", url, json={"style": "bogus"})).status_code == 422
        resp = await _call(client, alice, "POST", url, json={"style": "apa", "paper_ids": [stray]})
        assert resp.status_code == 404

    async def test_other_users_get_404_everywhere(
        self, client: AsyncClient, alice: Actor, bob: Actor
    ) -> None:
        project = await make_project(client, alice)
        pid = project["id"]
        paper_id = await paper(client, alice, pid)
        made = await _call(
            client,
            alice,
            "POST",
            f"/research/projects/{pid}/citations",
            json={"style": "apa", "paper_ids": [paper_id]},
        )
        cid = made.json()["data"][0]["id"]
        calls: list[tuple[str, str, dict[str, Any] | None]] = [
            ("POST", f"/research/projects/{pid}/citations", {"style": "apa"}),
            ("GET", f"/research/projects/{pid}/citations", None),
            ("GET", f"/research/projects/{pid}/citations/bibliography", None),
            ("GET", f"/research/citations/{cid}", None),
            ("DELETE", f"/research/citations/{cid}", None),
        ]
        for method, path, body in calls:
            resp = await _call(client, bob, method, path, json=body)
            assert resp.status_code == 404, (method, path, resp.status_code)
        assert (
            await _call(client, alice, "DELETE", f"/research/citations/{cid}")
        ).status_code == 204
