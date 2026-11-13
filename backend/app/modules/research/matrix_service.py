"""Evidence matrix service (Phase 7 M7.5). Ownership first (404 for anything not the caller's;
papers must also belong to the matrix's project). Three kinds of content are kept apart per cell
(`value_origin`): extracted paper information, AI interpretation and the researcher's own words.
A refresh from the analyses never overwrites a researcher value (spec 27.3)."""

from __future__ import annotations

import uuid
from collections import defaultdict

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research import (
    ResearchEvidenceMatrix,
    ResearchEvidenceMatrixColumn,
    ResearchEvidenceMatrixEntry,
    ResearchPaper,
)
from app.modules.research.matrix_schemas import (
    ResearchMatrixCellOut,
    ResearchMatrixColumnCreate,
    ResearchMatrixColumnOut,
    ResearchMatrixCreate,
    ResearchMatrixEvidenceOut,
    ResearchMatrixOut,
    ResearchMatrixPaperOut,
    ResearchMatrixPatch,
    ResearchMatrixRowOut,
    ResearchMatrixSummary,
)
from app.repositories.research_analysis_repository import ResearchAnalysisRepository
from app.repositories.research_matrix_repository import ResearchMatrixRepository
from app.repositories.research_paper_repository import ResearchPaperRepository
from app.repositories.research_project_repository import ResearchProjectRepository
from app.research.comparison import DIMENSIONS
from app.research.errors import (
    DuplicateColumnError,
    InvalidColumnOrderError,
    MatrixColumnNotFoundError,
    MatrixEntryNotFoundError,
    MatrixNotFoundError,
    PaperNotFoundError,
    ProjectArchivedError,
    ProjectNotFoundError,
)

# (key, title, source). Dimension sources reuse the comparison dimensions (M7.4).
DEFAULT_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("paper_title", "Paper title", "meta:title"),
    ("authors", "Authors", "meta:authors"),
    ("year", "Year", "meta:year"),
    ("research_problem", "Research problem", "dimension:research_problem"),
    ("objectives", "Objectives", "dimension:objectives"),
    ("methodology", "Methodology", "dimension:methodology"),
    ("dataset", "Dataset", "dimension:dataset"),
    ("model", "Model or algorithm", "dimension:models"),
    ("metrics", "Evaluation metrics", "dimension:metrics"),
    ("results", "Results", "dimension:results"),
    ("contributions", "Contributions", "dimension:contributions"),
    ("limitations", "Limitations", "dimension:limitations"),
    ("future_work", "Future work", "dimension:future_work"),
)
_DIMS = {d.key: d for d in DIMENSIONS}
MAX_EVIDENCE_PER_CELL = 8


class ResearchMatrixService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._repo = ResearchMatrixRepository(db)

    # helpers ─────────────────────────────────────────────────────────────────

    async def _matrix(self, user_id: uuid.UUID, matrix_id: uuid.UUID) -> ResearchEvidenceMatrix:
        row = await self._repo.get(user_id, matrix_id)
        if row is None:
            raise MatrixNotFoundError()
        return row

    async def _papers(
        self, user_id: uuid.UUID, project_id: uuid.UUID, ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, ResearchPaper]:
        found = await ResearchPaperRepository(self._db).get_many(user_id, project_id, ids)
        if len(found) != len(ids):
            raise PaperNotFoundError()
        return found

    async def _writable_project(self, user_id: uuid.UUID, project_id: uuid.UUID) -> None:
        project = await ResearchProjectRepository(self._db).get(user_id, project_id)
        if project is None:
            raise ProjectNotFoundError()
        if project.archived_at is not None:
            raise ProjectArchivedError()

    async def _extracted_cells(
        self, user_id: uuid.UUID, paper: ResearchPaper
    ) -> dict[str, tuple[str, list[str]]]:
        """source -> (text, evidence ids) from the paper record and its latest completed analysis.
        Nothing is invented: a dimension the analysis has no claim for stays empty."""
        cells: dict[str, tuple[str, list[str]]] = {
            "meta:title": (paper.title, []),
            "meta:authors": ("; ".join(paper.authors), []),
            "meta:year": (str(paper.publication_year) if paper.publication_year else "", []),
        }
        analyses = ResearchAnalysisRepository(self._db)
        run = await analyses.latest_completed(user_id, paper.id)
        sections = (run.structured_result or {}).get("sections", {}) if run else {}
        first_evidence: dict[tuple[str, int], str] = {}
        if run:
            for ev in await analyses.evidence_for(user_id, run.id):
                first_evidence.setdefault((ev.claim_type, ev.claim_index), str(ev.id))
        for key, dim in _DIMS.items():
            texts: list[str] = []
            evidence: list[str] = []
            for item in sections.get(dim.section, []):
                label = (item.get("label") or "").casefold()
                if dim.label_words and not any(w in label for w in dim.label_words):
                    continue
                texts.append(item["text"])
                ev_id = first_evidence.get((dim.section, item["index"]))
                if ev_id:
                    evidence.append(ev_id)
            cells[f"dimension:{key}"] = ("\n".join(texts), evidence[:MAX_EVIDENCE_PER_CELL])
        return cells

    async def _fill(
        self,
        user_id: uuid.UUID,
        matrix: ResearchEvidenceMatrix,
        papers: list[ResearchPaper],
        columns: list[ResearchEvidenceMatrixColumn],
    ) -> None:
        entries: list[ResearchEvidenceMatrixEntry] = []
        for paper in papers:
            cells = await self._extracted_cells(user_id, paper)
            for col in columns:
                text, evidence = cells.get(col.source or "", ("", []))
                entries.append(
                    ResearchEvidenceMatrixEntry(
                        user_id=user_id,
                        matrix_id=matrix.id,
                        research_paper_id=paper.id,
                        column_id=col.id,
                        value=text,
                        value_origin="extracted",
                        evidence_ids=evidence,
                    )
                )
        await self._repo.add_entries(entries)

    async def _out(self, user_id: uuid.UUID, matrix: ResearchEvidenceMatrix) -> ResearchMatrixOut:
        columns = await self._repo.columns(user_id, matrix.id)
        entries = await self._repo.entries(user_id, matrix.id)
        by_paper: dict[uuid.UUID, dict[uuid.UUID, ResearchEvidenceMatrixEntry]] = defaultdict(dict)
        wanted: set[uuid.UUID] = set()
        for e in entries:
            by_paper[e.research_paper_id][e.column_id] = e
            wanted.update(uuid.UUID(str(i)) for i in e.evidence_ids)
        evidence = await self._repo.evidence_by_ids(user_id, list(wanted))
        papers = await ResearchPaperRepository(self._db).get_many(
            user_id, matrix.research_project_id, list(by_paper)
        )
        rows: list[ResearchMatrixRowOut] = []
        for paper in sorted(papers.values(), key=lambda p: (p.created_at, p.id)):
            cells: list[ResearchMatrixCellOut] = []
            for col in columns:
                entry = by_paper[paper.id].get(col.id)
                ids = [uuid.UUID(str(i)) for i in (entry.evidence_ids if entry else [])]
                live = [evidence[i] for i in ids if i in evidence]
                cells.append(
                    ResearchMatrixCellOut(
                        column_id=col.id,
                        value=entry.value if entry else "",
                        origin=entry.value_origin if entry else "extracted",  # type: ignore[arg-type]
                        evidence=[
                            ResearchMatrixEvidenceOut(
                                id=ev.id,
                                quote=ev.supporting_text,
                                page_number=ev.page_number,
                                document_id=ev.document_id,
                            )
                            for ev in live
                        ],
                        stale_evidence=len(ids) - len(live),
                    )
                )
            rows.append(
                ResearchMatrixRowOut(
                    paper=ResearchMatrixPaperOut(
                        id=paper.id,
                        title=paper.title,
                        authors=list(paper.authors),
                        publication_year=paper.publication_year,
                    ),
                    cells=cells,
                )
            )
        return ResearchMatrixOut(
            id=matrix.id,
            research_project_id=matrix.research_project_id,
            title=matrix.title,
            description=matrix.description,
            columns=[
                ResearchMatrixColumnOut(
                    id=c.id,
                    column_key=c.column_key,
                    title=c.title,
                    position=c.position,
                    is_default=c.source is not None,
                )
                for c in columns
            ],
            rows=rows,
            created_at=matrix.created_at,
            updated_at=matrix.updated_at,
        )

    # matrices ────────────────────────────────────────────────────────────────

    async def create(
        self, user_id: uuid.UUID, project_id: uuid.UUID, body: ResearchMatrixCreate
    ) -> ResearchMatrixOut:
        await self._writable_project(user_id, project_id)
        papers = await self._papers(user_id, project_id, list(body.paper_ids))
        matrix = await self._repo.add(
            ResearchEvidenceMatrix(
                user_id=user_id,
                research_project_id=project_id,
                title=body.title,
                description=body.description or None,
            )
        )
        columns = [
            await self._repo.add_column(
                ResearchEvidenceMatrixColumn(
                    user_id=user_id,
                    matrix_id=matrix.id,
                    column_key=key,
                    title=title,
                    data_type="text",
                    position=i,
                    source=source,
                    configuration={},
                )
            )
            for i, (key, title, source) in enumerate(DEFAULT_COLUMNS)
        ]
        await self._fill(user_id, matrix, [papers[i] for i in body.paper_ids], columns)
        await self._db.commit()
        return await self._out(user_id, matrix)

    async def list(
        self, user_id: uuid.UUID, project_id: uuid.UUID, *, limit: int, offset: int
    ) -> tuple[list[ResearchMatrixSummary], int]:
        if await ResearchProjectRepository(self._db).get(user_id, project_id) is None:
            raise ProjectNotFoundError()
        rows, total = await self._repo.list_for_project(
            user_id, project_id, limit=limit, offset=offset
        )
        counts = await self._repo.count_papers([r.id for r in rows])
        return [
            ResearchMatrixSummary(
                id=r.id,
                research_project_id=r.research_project_id,
                title=r.title,
                description=r.description,
                paper_count=counts.get(r.id, 0),
                updated_at=r.updated_at,
            )
            for r in rows
        ], total

    async def get(self, user_id: uuid.UUID, matrix_id: uuid.UUID) -> ResearchMatrixOut:
        return await self._out(user_id, await self._matrix(user_id, matrix_id))

    async def patch(
        self, user_id: uuid.UUID, matrix_id: uuid.UUID, body: ResearchMatrixPatch
    ) -> ResearchMatrixOut:
        matrix = await self._matrix(user_id, matrix_id)
        await self._writable_project(user_id, matrix.research_project_id)
        if body.title is not None:
            matrix.title = body.title
        if "description" in body.model_fields_set:
            matrix.description = body.description or None
        await self._db.commit()
        await self._db.refresh(matrix)  # updated_at is set by the database
        return await self._out(user_id, matrix)

    async def delete(self, user_id: uuid.UUID, matrix_id: uuid.UUID) -> None:
        await self._matrix(user_id, matrix_id)
        await self._repo.delete(user_id, matrix_id)
        await self._db.commit()

    # papers ──────────────────────────────────────────────────────────────────

    async def add_papers(
        self, user_id: uuid.UUID, matrix_id: uuid.UUID, paper_ids: list[uuid.UUID]
    ) -> ResearchMatrixOut:
        matrix = await self._matrix(user_id, matrix_id)
        await self._writable_project(user_id, matrix.research_project_id)
        papers = await self._papers(user_id, matrix.research_project_id, paper_ids)
        present = {e.research_paper_id for e in await self._repo.entries(user_id, matrix_id)}
        fresh = [papers[i] for i in paper_ids if i not in present]
        await self._fill(user_id, matrix, fresh, await self._repo.columns(user_id, matrix_id))
        await self._db.commit()
        return await self._out(user_id, matrix)

    async def remove_paper(
        self, user_id: uuid.UUID, matrix_id: uuid.UUID, paper_id: uuid.UUID
    ) -> ResearchMatrixOut:
        matrix = await self._matrix(user_id, matrix_id)
        await self._writable_project(user_id, matrix.research_project_id)
        if not await self._repo.remove_paper(user_id, matrix_id, paper_id):
            raise MatrixEntryNotFoundError()
        await self._db.commit()
        return await self._out(user_id, matrix)

    # columns ─────────────────────────────────────────────────────────────────

    async def _check_title(
        self, user_id: uuid.UUID, matrix_id: uuid.UUID, title: str, own: uuid.UUID | None = None
    ) -> None:
        for col in await self._repo.columns(user_id, matrix_id):
            if col.id != own and col.title.casefold() == title.casefold():
                raise DuplicateColumnError()

    async def add_column(
        self, user_id: uuid.UUID, matrix_id: uuid.UUID, body: ResearchMatrixColumnCreate
    ) -> ResearchMatrixOut:
        matrix = await self._matrix(user_id, matrix_id)
        await self._writable_project(user_id, matrix.research_project_id)
        await self._check_title(user_id, matrix_id, body.title)
        columns = await self._repo.columns(user_id, matrix_id)
        column = await self._repo.add_column(
            ResearchEvidenceMatrixColumn(
                user_id=user_id,
                matrix_id=matrix_id,
                column_key=f"custom_{uuid.uuid4().hex[:10]}",
                title=body.title,
                data_type="text",
                position=len(columns),
                source=None,
                configuration={},
            )
        )
        paper_ids = sorted(
            {e.research_paper_id for e in await self._repo.entries(user_id, matrix_id)}
        )
        await self._repo.add_entries(
            [
                ResearchEvidenceMatrixEntry(
                    user_id=user_id,
                    matrix_id=matrix_id,
                    research_paper_id=pid,
                    column_id=column.id,
                    value="",
                    value_origin="researcher",
                    evidence_ids=[],
                )
                for pid in paper_ids
            ]
        )
        await self._db.commit()
        return await self._out(user_id, matrix)

    async def rename_column(
        self, user_id: uuid.UUID, matrix_id: uuid.UUID, column_id: uuid.UUID, title: str
    ) -> ResearchMatrixOut:
        matrix = await self._matrix(user_id, matrix_id)
        await self._writable_project(user_id, matrix.research_project_id)
        column = await self._repo.get_column(user_id, matrix_id, column_id)
        if column is None:
            raise MatrixColumnNotFoundError()
        await self._check_title(user_id, matrix_id, title, own=column.id)
        column.title = title
        await self._db.commit()
        return await self._out(user_id, matrix)

    async def remove_column(
        self, user_id: uuid.UUID, matrix_id: uuid.UUID, column_id: uuid.UUID
    ) -> ResearchMatrixOut:
        matrix = await self._matrix(user_id, matrix_id)
        await self._writable_project(user_id, matrix.research_project_id)
        if await self._repo.get_column(user_id, matrix_id, column_id) is None:
            raise MatrixColumnNotFoundError()
        await self._repo.delete_column(user_id, column_id)
        for i, col in enumerate(await self._repo.columns(user_id, matrix_id)):
            col.position = i
        await self._db.commit()
        return await self._out(user_id, matrix)

    async def reorder_columns(
        self, user_id: uuid.UUID, matrix_id: uuid.UUID, ids: list[uuid.UUID]
    ) -> ResearchMatrixOut:
        matrix = await self._matrix(user_id, matrix_id)
        await self._writable_project(user_id, matrix.research_project_id)
        columns = {c.id: c for c in await self._repo.columns(user_id, matrix_id)}
        if set(ids) != set(columns) or len(ids) != len(columns):
            raise InvalidColumnOrderError()
        for position, cid in enumerate(ids):
            columns[cid].position = position
        await self._db.commit()
        return await self._out(user_id, matrix)

    # entries ─────────────────────────────────────────────────────────────────

    async def edit_entry(
        self,
        user_id: uuid.UUID,
        matrix_id: uuid.UUID,
        paper_id: uuid.UUID,
        column_id: uuid.UUID,
        value: str,
    ) -> ResearchMatrixOut:
        matrix = await self._matrix(user_id, matrix_id)
        await self._writable_project(user_id, matrix.research_project_id)
        entry = await self._repo.get_entry(user_id, matrix_id, paper_id, column_id)
        if entry is None:
            raise MatrixEntryNotFoundError()
        # The researcher's words replace the cell; its evidence links are kept so the claim stays
        # traceable. The origin records who wrote the current value.
        entry.value = value
        entry.value_origin = "researcher"
        await self._db.commit()
        return await self._out(user_id, matrix)

    async def refresh(self, user_id: uuid.UUID, matrix_id: uuid.UUID) -> ResearchMatrixOut:
        """Re-read the analyses. Only cells still holding extracted values change; researcher and
        AI-interpretation values are never overwritten."""
        matrix = await self._matrix(user_id, matrix_id)
        await self._writable_project(user_id, matrix.research_project_id)
        columns = {c.id: c for c in await self._repo.columns(user_id, matrix_id)}
        entries = await self._repo.entries(user_id, matrix_id)
        papers = await ResearchPaperRepository(self._db).get_many(
            user_id, matrix.research_project_id, sorted({e.research_paper_id for e in entries})
        )
        cache: dict[uuid.UUID, dict[str, tuple[str, list[str]]]] = {}
        for e in entries:
            col = columns.get(e.column_id)
            paper = papers.get(e.research_paper_id)
            if e.value_origin != "extracted" or col is None or col.source is None or paper is None:
                continue
            if paper.id not in cache:
                cache[paper.id] = await self._extracted_cells(user_id, paper)
            text, evidence = cache[paper.id].get(col.source, ("", []))
            e.value, e.evidence_ids = text, evidence
        await self._db.commit()
        return await self._out(user_id, matrix)
