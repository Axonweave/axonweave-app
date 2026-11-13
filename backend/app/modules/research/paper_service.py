"""Paper library service (Phase 7 M7.2). Ownership is resolved here: a project, paper or document
that is not the caller's is a 404 (CLAUDE.md rules 1 to 3). Duplicate detection only suggests; a
merge happens only on an explicit request."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research import ResearchPaper
from app.modules.research.paper_schemas import (
    DuplicateCandidateOut,
    DuplicatePaperOut,
    DuplicateResolve,
    PaperCreate,
    PaperOut,
    PaperPatch,
)
from app.repositories.document_repository import DocumentRepository
from app.repositories.research_paper_repository import ResearchPaperRepository, Row
from app.repositories.research_project_repository import ResearchProjectRepository
from app.research.errors import (
    DocumentAlreadyLinkedError,
    DocumentNotFoundError,
    DuplicateDoiError,
    InvalidMergeError,
    PaperArchivedError,
    PaperNotArchivedError,
    PaperNotFoundError,
    ProjectNotFoundError,
)
from app.research.papers import PaperFacts, candidates, doi_url, normalise_title

MERGE_FILL = (
    "abstract",
    "publication_year",
    "venue",
    "publisher",
    "doi",
    "url",
    "volume",
    "issue",
    "pages",
    "document_id",
)


def to_out(row: Row) -> PaperOut:
    p, doc_name, doc_status = row
    return PaperOut(
        id=p.id,
        research_project_id=p.research_project_id,
        document_id=p.document_id,
        document_name=doc_name,
        processing_status=doc_status,
        analysis_status=p.analysis_status,
        title=p.title,
        abstract=p.abstract,
        authors=list(p.authors),
        publication_year=p.publication_year,
        venue=p.venue,
        publisher=p.publisher,
        doi=p.doi,
        url=p.url,
        keywords=list(p.keywords),
        volume=p.volume,
        issue=p.issue,
        pages=p.pages,
        metadata_source=p.metadata_source,
        metadata_verified=p.metadata_verified,
        status=p.status,
        archived_at=p.archived_at,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


class ResearchPaperService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._repo = ResearchPaperRepository(db)

    async def _project(self, user_id: uuid.UUID, project_id: uuid.UUID) -> None:
        if await ResearchProjectRepository(self._db).get(user_id, project_id) is None:
            raise ProjectNotFoundError()

    async def _row(self, user_id: uuid.UUID, paper_id: uuid.UUID) -> Row:
        row = await self._repo.get(user_id, paper_id)
        if row is None:
            raise PaperNotFoundError()
        return row

    async def _check_document(
        self,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        document_id: uuid.UUID,
        except_id: uuid.UUID | None = None,
    ) -> None:
        doc = await DocumentRepository(self._db).get_owned(document_id=document_id, user_id=user_id)
        if doc is None:
            raise DocumentNotFoundError()
        if await self._repo.document_linked(user_id, project_id, document_id, except_id=except_id):
            raise DocumentAlreadyLinkedError()

    async def create(self, user_id: uuid.UUID, project_id: uuid.UUID, body: PaperCreate) -> Row:
        await self._project(user_id, project_id)
        if body.doi and await self._repo.doi_taken(user_id, project_id, body.doi):
            raise DuplicateDoiError()
        if body.document_id:
            await self._check_document(user_id, project_id, body.document_id)
        data = body.model_dump()
        if data["doi"] and not data["url"]:
            data["url"] = doi_url(data["doi"])
        paper = await self._repo.add(
            ResearchPaper(
                user_id=user_id,
                research_project_id=project_id,
                title_normalised=normalise_title(body.title),
                metadata_source="user_supplied",
                **data,
            )
        )
        await self._db.commit()
        return await self._row(user_id, paper.id)

    async def get(self, user_id: uuid.UUID, paper_id: uuid.UUID) -> Row:
        return await self._row(user_id, paper_id)

    async def list(
        self,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        *,
        q: str | None,
        status: str | None,
        year: int | None,
        has_file: bool | None,
        archived: bool,
        sort_by: str,
        descending: bool,
        limit: int,
        offset: int,
    ) -> tuple[list[Row], int]:
        await self._project(user_id, project_id)
        return await self._repo.list_for_project(
            user_id,
            project_id,
            q=q,
            status=status,
            year=year,
            has_file=has_file,
            archived=archived,
            sort_by=sort_by,
            descending=descending,
            limit=limit,
            offset=offset,
        )

    async def update(self, user_id: uuid.UUID, paper_id: uuid.UUID, body: PaperPatch) -> Row:
        paper, _, _ = await self._row(user_id, paper_id)
        if paper.archived_at is not None:
            raise PaperArchivedError()
        changes: dict[str, Any] = body.model_dump(exclude_unset=True)
        for required in ("title", "authors", "keywords", "status", "metadata_verified"):
            if required in changes and changes[required] is None:
                del changes[required]
        if changes.get("doi") and changes["doi"] != paper.doi:
            if await self._repo.doi_taken(
                user_id, paper.research_project_id, changes["doi"], except_id=paper.id
            ):
                raise DuplicateDoiError()
        if changes.get("document_id") and changes["document_id"] != paper.document_id:
            await self._check_document(
                user_id, paper.research_project_id, changes["document_id"], except_id=paper.id
            )
        if "title" in changes:
            paper.title_normalised = normalise_title(changes["title"])
        metadata_fields = set(changes) - {"status", "metadata_verified", "document_id"}
        for key, value in changes.items():
            setattr(paper, key, value)
        if metadata_fields:
            # A user edit makes the user the source; verification is theirs to set.
            paper.metadata_source = "user_supplied"
            if "metadata_verified" not in changes:
                paper.metadata_verified = False
        await self._db.commit()
        return await self._row(user_id, paper_id)

    async def archive(self, user_id: uuid.UUID, paper_id: uuid.UUID) -> Row:
        paper, _, _ = await self._row(user_id, paper_id)
        if paper.archived_at is None:
            paper.archived_at = datetime.now(UTC)
            await self._db.commit()
        return await self._row(user_id, paper_id)

    async def restore(self, user_id: uuid.UUID, paper_id: uuid.UUID) -> Row:
        paper, _, _ = await self._row(user_id, paper_id)
        if paper.archived_at is None:
            raise PaperNotArchivedError()
        paper.archived_at = None
        await self._db.commit()
        return await self._row(user_id, paper_id)

    async def delete(self, user_id: uuid.UUID, paper_id: uuid.UUID) -> None:
        """Removes the library record only. A linked document stays in the document library."""
        await self._row(user_id, paper_id)
        await self._repo.delete(user_id, paper_id)
        await self._db.commit()

    # duplicates ───────────────────────────────────────────────────────────────

    async def duplicates(
        self, user_id: uuid.UUID, project_id: uuid.UUID
    ) -> list[DuplicateCandidateOut]:
        await self._project(user_id, project_id)
        papers = await self._repo.all_for_duplicates(user_id, project_id)
        facts = [
            PaperFacts(
                p.id, p.title, p.title_normalised, list(p.authors), p.publication_year, p.doi
            )
            for p in papers
        ]
        found = candidates(facts, await self._repo.dismissed_pairs(user_id, project_id))
        by_id = {p.id: p for p in papers}

        def brief(p: ResearchPaper) -> DuplicatePaperOut:
            return DuplicatePaperOut(
                id=p.id,
                title=p.title,
                authors=list(p.authors),
                publication_year=p.publication_year,
                doi=p.doi,
                has_file=p.document_id is not None,
            )

        return [
            DuplicateCandidateOut(
                paper_a=brief(by_id[c.paper_a]),
                paper_b=brief(by_id[c.paper_b]),
                reason=c.reason,
                score=c.score,
                shared_authors=c.shared_authors,
                same_year=c.same_year,
            )
            for c in found
        ]

    async def resolve_duplicate(
        self, user_id: uuid.UUID, project_id: uuid.UUID, body: DuplicateResolve
    ) -> PaperOut | None:
        await self._project(user_id, project_id)
        if body.paper_id == body.other_id:
            raise InvalidMergeError()
        papers = await self._repo.get_many(user_id, project_id, [body.paper_id, body.other_id])
        if len(papers) != 2:
            raise PaperNotFoundError()
        if body.action == "not_duplicate":
            await self._repo.dismiss_pair(user_id, project_id, body.paper_id, body.other_id)
            await self._db.commit()
            return None
        if body.survivor_id not in (body.paper_id, body.other_id):
            raise InvalidMergeError()
        survivor = papers[body.survivor_id]
        merged = papers[body.other_id if body.survivor_id == body.paper_id else body.paper_id]
        # Copy only what the survivor lacks; the survivor's own values always win.
        fill = {k: getattr(merged, k) for k in MERGE_FILL if getattr(survivor, k) is None}
        fill = {k: v for k, v in fill.items() if v is not None}
        keywords = list(dict.fromkeys([*survivor.keywords, *merged.keywords]))[:30]
        authors = list(survivor.authors) or list(merged.authors)
        # remove the other record first so unique DOI / document links are free to move
        await self._repo.delete(user_id, merged.id)
        await self._db.flush()
        for key, value in fill.items():
            setattr(survivor, key, value)
        survivor.keywords = keywords
        survivor.authors = authors
        await self._db.commit()
        return to_out(await self._row(user_id, survivor.id))
