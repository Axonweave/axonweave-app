"""Citation service (Phase 7 M7.8). Citations are formatted by `app.research.citations` from the
paper's recorded metadata; no model is involved and missing details are reported, not invented.
Generating again refreshes a citation from the paper's current metadata (spec 30.5)."""

from __future__ import annotations

import re
import uuid
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research import ResearchCitation, ResearchPaper
from app.modules.research.citation_schemas import (
    ResearchBibliographyOut,
    ResearchCitationIssue,
    ResearchCitationOut,
)
from app.repositories.research_citation_repository import ResearchCitationRepository
from app.repositories.research_paper_repository import ResearchPaperRepository
from app.repositories.research_project_repository import ResearchProjectRepository
from app.research.citations import Meta, format_citation, in_text, sort_key, validate
from app.research.errors import (
    CitationNotFoundError,
    PaperNotFoundError,
    ProjectArchivedError,
    ProjectNotFoundError,
)

_BIB_ESCAPE = re.compile(r"([&%#_$])")


def meta_of(paper: ResearchPaper, accessed: date | None) -> Meta:
    return Meta(
        authors=tuple(str(a) for a in paper.authors),
        title=paper.title,
        year=paper.publication_year,
        venue=paper.venue,
        publisher=paper.publisher,
        doi=paper.doi,
        url=paper.url,
        volume=paper.volume,
        issue=paper.issue,
        pages=paper.pages,
        accessed=accessed,
        verified=paper.metadata_verified,
    )


def _bib_value(value: str) -> str:
    return _BIB_ESCAPE.sub(r"\\\1", value.replace("{", "").replace("}", "").replace("\\", ""))


def bibtex_entry(key: str, meta: Meta) -> str:
    fields: list[tuple[str, str | None]] = [
        ("author", " and ".join(_bib_value(a) for a in meta.authors) or None),
        ("title", "{" + _bib_value(meta.title) + "}"),
        ("journal", _bib_value(meta.venue) if meta.venue else None),
        ("publisher", _bib_value(meta.publisher) if meta.publisher else None),
        ("year", str(meta.year) if meta.year else None),
        ("volume", _bib_value(meta.volume) if meta.volume else None),
        ("number", _bib_value(meta.issue) if meta.issue else None),
        ("pages", _bib_value(meta.pages).replace("–", "--") if meta.pages else None),
        ("doi", meta.doi),
        ("url", meta.url),
    ]
    body = ",\n".join(
        f"  {k} = {{{v}}}" if k != "title" else f"  {k} = {v}" for k, v in fields if v
    )
    return f"@article{{{key},\n{body}\n}}"


class ResearchCitationService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._repo = ResearchCitationRepository(db)

    async def _project(self, user_id: uuid.UUID, project_id: uuid.UUID, *, write: bool) -> None:
        project = await ResearchProjectRepository(self._db).get(user_id, project_id)
        if project is None:
            raise ProjectNotFoundError()
        if write and project.archived_at is not None:
            raise ProjectArchivedError()

    async def _papers(
        self, user_id: uuid.UUID, project_id: uuid.UUID, ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, ResearchPaper]:
        return await ResearchPaperRepository(self._db).get_many(user_id, project_id, ids)

    async def _out(
        self, user_id: uuid.UUID, project_id: uuid.UUID, rows: list[ResearchCitation]
    ) -> list[ResearchCitationOut]:
        papers = await self._papers(user_id, project_id, list({r.research_paper_id for r in rows}))
        out: list[ResearchCitationOut] = []
        for r in rows:
            snap = Meta.from_snapshot(r.metadata_snapshot)
            paper = papers.get(r.research_paper_id)
            issues = validate(snap)
            current = meta_of(paper, snap.accessed).snapshot() if paper else None
            out.append(
                ResearchCitationOut(
                    id=r.id,
                    research_project_id=r.research_project_id,
                    research_paper_id=r.research_paper_id,
                    paper_title=paper.title if paper else snap.title,
                    citation_style=r.citation_style,
                    formatted_citation=r.formatted_citation,
                    in_text_citation=r.in_text_citation,
                    metadata=r.metadata_snapshot,
                    issues=[ResearchCitationIssue(**i.__dict__) for i in issues],
                    complete=not any(i.severity in ("missing", "warning") for i in issues),
                    metadata_changed=current is not None and current != r.metadata_snapshot,
                    created_at=r.created_at,
                    updated_at=r.updated_at,
                )
            )
        return out

    async def generate(
        self,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        style: str,
        paper_ids: list[uuid.UUID] | None,
        accessed: date | None,
    ) -> list[ResearchCitationOut]:
        await self._project(user_id, project_id, write=True)
        papers_repo = ResearchPaperRepository(self._db)
        if paper_ids is None:
            rows, _ = await papers_repo.list_for_project(
                user_id,
                project_id,
                q=None,
                status=None,
                year=None,
                has_file=None,
                archived=False,
                sort_by="created_at",
                descending=False,
                limit=100,
                offset=0,
            )
            papers = {r[0].id: r[0] for r in rows}
            ordered = list(papers)
        else:
            papers = await self._papers(user_id, project_id, paper_ids)
            if len(papers) != len(set(paper_ids)):
                raise PaperNotFoundError()
            ordered = list(dict.fromkeys(paper_ids))
        saved: list[ResearchCitation] = []
        for pid in ordered:
            meta = meta_of(papers[pid], accessed)
            existing = await self._repo.get_for_paper(user_id, project_id, pid, style)
            text = format_citation(style, meta)
            short = in_text(style, meta)
            if existing is None:
                existing = await self._repo.add(
                    ResearchCitation(
                        user_id=user_id,
                        research_project_id=project_id,
                        research_paper_id=pid,
                        citation_style=style,
                        formatted_citation=text,
                        in_text_citation=short,
                        metadata_snapshot=meta.snapshot(),
                    )
                )
            else:
                existing.formatted_citation = text
                existing.in_text_citation = short
                existing.metadata_snapshot = meta.snapshot()
            saved.append(existing)
        await self._db.commit()
        for row in saved:
            await self._db.refresh(row)
        return await self._out(user_id, project_id, saved)

    async def list(
        self, user_id: uuid.UUID, project_id: uuid.UUID, style: str | None
    ) -> list[ResearchCitationOut]:
        await self._project(user_id, project_id, write=False)
        rows = await self._repo.list_for_project(user_id, project_id, style)
        return await self._out(user_id, project_id, rows)

    async def get(self, user_id: uuid.UUID, citation_id: uuid.UUID) -> ResearchCitationOut:
        row = await self._repo.get(user_id, citation_id)
        if row is None:
            raise CitationNotFoundError()
        return (await self._out(user_id, row.research_project_id, [row]))[0]

    async def delete(self, user_id: uuid.UUID, citation_id: uuid.UUID) -> None:
        row = await self._repo.get(user_id, citation_id)
        if row is None:
            raise CitationNotFoundError()
        await self._project(user_id, row.research_project_id, write=True)
        await self._repo.delete(user_id, citation_id)
        await self._db.commit()

    async def bibliography(
        self, user_id: uuid.UUID, project_id: uuid.UUID, style: str, fmt: str
    ) -> ResearchBibliographyOut:
        await self._project(user_id, project_id, write=False)
        rows = await self._repo.list_for_project(user_id, project_id, style)
        items = sorted(
            ((Meta.from_snapshot(r.metadata_snapshot), r) for r in rows),
            key=lambda pair: sort_key(pair[0]),
        )
        if fmt == "bibtex":
            used: set[str] = set()
            entries = []
            for meta, _ in items:
                base = (
                    re.sub(
                        r"[^a-z0-9]",
                        "",
                        (
                            meta.authors[0].split(",")[0].split()[-1] if meta.authors else "ref"
                        ).casefold(),
                    )
                    or "ref"
                )
                key = f"{base}{meta.year or ''}"
                n = 1
                while key in used:
                    n += 1
                    key = f"{base}{meta.year or ''}{chr(96 + min(n, 26))}"
                used.add(key)
                entries.append(bibtex_entry(key, meta))
            content = "\n\n".join(entries)
            filename = "bibliography.bib"
        else:
            lines = [
                (f"[{i}] " if style == "ieee" else "") + r.formatted_citation
                for i, (_, r) in enumerate(items, start=1)
            ]
            content = "\n\n".join(lines)
            filename = f"bibliography-{style}.txt"
        return ResearchBibliographyOut(
            style=style, format=fmt, filename=filename, count=len(items), content=content
        )
