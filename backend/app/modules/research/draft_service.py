"""Draft service (Phase 7 M7.9). Ownership first (404 for anything not the caller's). A draft is
never silently overwritten: a content or title change needs the version the researcher was
editing, every saved state is a version, and a restore adds a new version instead of rewriting
history. AI suggestions are returned, not saved: accepting one is an ordinary edit with change
source `ai_suggestion` (spec 31.6)."""

from __future__ import annotations

import re
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.orchestration.runtime import AiRuntime
from app.models.research import ResearchDraft, ResearchDraftVersion
from app.modules.research.citation_service import meta_of
from app.modules.research.claim_loader import load_analysed_papers, load_available
from app.modules.research.draft_schemas import (
    ResearchDraftCheckOut,
    ResearchDraftCreate,
    ResearchDraftExportOut,
    ResearchDraftOut,
    ResearchDraftPatch,
    ResearchDraftSentenceCheck,
    ResearchDraftSummary,
    ResearchDraftVersionOut,
    ResearchDraftVersionSummary,
    ResearchWritingOut,
    ResearchWritingRequest,
    ResearchWritingSource,
)
from app.repositories.research_draft_repository import ResearchDraftRepository
from app.repositories.research_gap_repository import ResearchGapRepository
from app.repositories.research_paper_repository import ResearchPaperRepository
from app.repositories.research_project_repository import ResearchProjectRepository
from app.research.claims import LoadedPaper
from app.research.drafts import (
    SentenceCheck,
    check_sentences,
    cited_ids,
    render_markdown,
    summarise,
)
from app.research.errors import (
    AssistInputError,
    DraftInvalidReferencesError,
    DraftNotFoundError,
    DraftVersionConflictError,
    DraftVersionNotFoundError,
    NoEvidenceError,
    ProjectArchivedError,
    ProjectNotFoundError,
)
from app.research.writing_assist import (
    EDIT_ACTIONS,
    WritingAssistant,
    apply_numbers,
    build_sources,
    build_turn,
    finish,
    to_numbered,
)

_WORDS = re.compile(r"\w+", re.UNICODE)


def _summary(d: ResearchDraft) -> ResearchDraftSummary:
    return ResearchDraftSummary(
        id=d.id,
        research_project_id=d.research_project_id,
        title=d.title,
        document_type=d.document_type,
        status=d.status,
        citation_style=d.citation_style,
        version_number=d.version_number,
        word_count=len(_WORDS.findall(d.content)),
        created_at=d.created_at,
        updated_at=d.updated_at,
    )


def _out(d: ResearchDraft) -> ResearchDraftOut:
    return ResearchDraftOut(**_summary(d).model_dump(), content=d.content)


def _checks_out(checks: list[SentenceCheck]) -> list[ResearchDraftSentenceCheck]:
    return [
        ResearchDraftSentenceCheck(text=c.text, status=c.status, paper_ids=c.paper_ids)
        for c in checks
    ]


def _file_stem(title: str) -> str:
    return re.sub(r"[^\w-]+", "_", title)[:60] or "draft"


class ResearchDraftService:
    def __init__(self, db: AsyncSession, runtime: AiRuntime | None = None) -> None:
        self._db = db
        self._runtime = runtime
        self._repo = ResearchDraftRepository(db)

    async def _project(self, user_id: uuid.UUID, project_id: uuid.UUID, *, write: bool) -> None:
        project = await ResearchProjectRepository(self._db).get(user_id, project_id)
        if project is None:
            raise ProjectNotFoundError()
        if write and project.archived_at is not None:
            raise ProjectArchivedError()

    async def _get(self, user_id: uuid.UUID, draft_id: uuid.UUID) -> ResearchDraft:
        draft = await self._repo.get(user_id, draft_id)
        if draft is None:
            raise DraftNotFoundError()
        return draft

    async def _save_version(
        self, draft: ResearchDraft, source: str, summary: str
    ) -> ResearchDraftVersion:
        return await self._repo.add_version(
            ResearchDraftVersion(
                user_id=draft.user_id,
                draft_id=draft.id,
                version_number=draft.version_number,
                title_snapshot=draft.title,
                content_snapshot=draft.content,
                change_summary=summary[:300],
                change_source=source,
            )
        )

    # drafts ──────────────────────────────────────────────────────────────────

    async def create(
        self, user_id: uuid.UUID, project_id: uuid.UUID, body: ResearchDraftCreate
    ) -> ResearchDraftOut:
        await self._project(user_id, project_id, write=True)
        draft = await self._repo.add(
            ResearchDraft(
                user_id=user_id,
                research_project_id=project_id,
                title=body.title,
                document_type=body.document_type,
                content=body.content,
                status="draft",
                citation_style=body.citation_style,
                version_number=1,
            )
        )
        await self._save_version(draft, "created", "Draft created")
        await self._db.commit()
        await self._db.refresh(draft)
        return _out(draft)

    async def list(
        self,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        *,
        status: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[ResearchDraftSummary], int]:
        await self._project(user_id, project_id, write=False)
        rows, total = await self._repo.list_for_project(
            user_id, project_id, status=status, limit=limit, offset=offset
        )
        return [_summary(d) for d in rows], total

    async def get(self, user_id: uuid.UUID, draft_id: uuid.UUID) -> ResearchDraftOut:
        return _out(await self._get(user_id, draft_id))

    async def patch(
        self, user_id: uuid.UUID, draft_id: uuid.UUID, body: ResearchDraftPatch
    ) -> ResearchDraftOut:
        draft = await self._get(user_id, draft_id)
        await self._project(user_id, draft.research_project_id, write=True)
        changes = body.model_dump(exclude_unset=True)
        changed_text = False
        if body.title is not None or body.content is not None:
            if body.expected_version != draft.version_number:
                raise DraftVersionConflictError()
            changed_text = (body.title is not None and body.title != draft.title) or (
                body.content is not None and body.content != draft.content
            )
        for key in ("document_type", "status", "citation_style"):
            if changes.get(key) is not None:
                setattr(draft, key, changes[key])
        if changed_text:
            if body.title is not None:
                draft.title = body.title
            if body.content is not None:
                draft.content = body.content
            draft.version_number += 1
            default = (
                "AI suggestion accepted" if body.change_source == "ai_suggestion" else "Edited"
            )
            await self._save_version(
                draft, body.change_source, (body.change_summary or default).strip()
            )
        await self._db.commit()
        await self._db.refresh(draft)
        return _out(draft)

    async def delete(self, user_id: uuid.UUID, draft_id: uuid.UUID) -> None:
        draft = await self._get(user_id, draft_id)
        await self._project(user_id, draft.research_project_id, write=True)
        await self._repo.delete(user_id, draft_id)
        await self._db.commit()

    # versions ────────────────────────────────────────────────────────────────

    async def versions(
        self, user_id: uuid.UUID, draft_id: uuid.UUID
    ) -> list[ResearchDraftVersionSummary]:
        await self._get(user_id, draft_id)
        return [
            ResearchDraftVersionSummary(
                version_number=v.version_number,
                title=v.title_snapshot,
                change_summary=v.change_summary,
                change_source=v.change_source,
                characters=len(v.content_snapshot),
                created_at=v.created_at,
            )
            for v in await self._repo.versions(user_id, draft_id)
        ]

    async def version(
        self, user_id: uuid.UUID, draft_id: uuid.UUID, number: int
    ) -> ResearchDraftVersionOut:
        await self._get(user_id, draft_id)
        v = await self._repo.version(user_id, draft_id, number)
        if v is None:
            raise DraftVersionNotFoundError()
        return ResearchDraftVersionOut(
            version_number=v.version_number,
            title=v.title_snapshot,
            change_summary=v.change_summary,
            change_source=v.change_source,
            characters=len(v.content_snapshot),
            created_at=v.created_at,
            content=v.content_snapshot,
        )

    async def restore(
        self, user_id: uuid.UUID, draft_id: uuid.UUID, number: int, expected_version: int
    ) -> ResearchDraftOut:
        draft = await self._get(user_id, draft_id)
        await self._project(user_id, draft.research_project_id, write=True)
        if expected_version != draft.version_number:
            raise DraftVersionConflictError()
        old = await self._repo.version(user_id, draft_id, number)
        if old is None:
            raise DraftVersionNotFoundError()
        draft.title = old.title_snapshot
        draft.content = old.content_snapshot
        draft.version_number += 1
        await self._save_version(draft, "restore", f"Restored version {number}")
        await self._db.commit()
        await self._db.refresh(draft)
        return _out(draft)

    # evidence check, preview and export ──────────────────────────────────────

    async def check(self, user_id: uuid.UUID, draft_id: uuid.UUID) -> ResearchDraftCheckOut:
        draft = await self._get(user_id, draft_id)
        project_ids, analysed = await load_available(
            self._db, user_id, draft.research_project_id, cited_ids(draft.content)
        )
        checks = check_sentences(draft.content, project_ids, analysed)
        invalid = [i for i in cited_ids(draft.content) if i not in project_ids]
        return ResearchDraftCheckOut(
            checks=_checks_out(checks), summary=summarise(checks), invalid_references=invalid
        )

    async def render(
        self, user_id: uuid.UUID, draft_id: uuid.UUID, *, strict: bool
    ) -> ResearchDraftExportOut:
        draft = await self._get(user_id, draft_id)
        ids = cited_ids(draft.content)
        papers = (
            await ResearchPaperRepository(self._db).get_many(
                user_id, draft.research_project_id, ids
            )
            if ids
            else {}
        )
        metas = {pid: meta_of(p, None) for pid, p in papers.items()}
        rendered = render_markdown(draft.title, draft.content, metas, draft.citation_style)
        if strict and rendered.invalid:
            raise DraftInvalidReferencesError()
        return ResearchDraftExportOut(
            format="markdown",
            filename=_file_stem(draft.title) + ".md",
            content=rendered.markdown,
            cited_count=len(rendered.cited),
            invalid_references=rendered.invalid,
        )

    # writing assistance ──────────────────────────────────────────────────────

    async def assist(
        self, user_id: uuid.UUID, draft_id: uuid.UUID, body: ResearchWritingRequest
    ) -> ResearchWritingOut:
        if self._runtime is None:
            raise RuntimeError("assist needs the AI runtime")
        draft = await self._get(user_id, draft_id)
        project_id = draft.research_project_id
        await self._project(user_id, project_id, write=True)
        editing = body.action in EDIT_ACTIONS
        if (editing or body.action == "expand") and not body.selected_text.strip():
            raise AssistInputError()
        assistant = WritingAssistant(self._db, self._runtime)
        if not assistant.available:
            from app.ai.errors import LLMNotConfiguredError

            raise LLMNotConfiguredError()
        await assistant.enforce_limits(user_id)

        text = body.selected_text
        project_ids, cited_analysed = await load_available(
            self._db, user_id, project_id, cited_ids(text)
        )
        papers: list[LoadedPaper] = []
        sources = []
        numbers: dict[int, uuid.UUID] = {}
        cited_titles: list[str] = []
        if editing:
            order = [pid for pid in cited_ids(text) if pid in project_ids]
            found = await ResearchPaperRepository(self._db).get_many(user_id, project_id, order)
            cited_titles = [found[pid].title for pid in order]
            numbers = dict(enumerate(order, start=1))
            text = to_numbered(text, order)
        else:
            papers = await load_analysed_papers(self._db, user_id, project_id, body.paper_ids)
            sources = build_sources(papers, body.section)
            if not sources:
                raise NoEvidenceError()
            numbers = {s.n: s.paper_id for s in sources}
            first = {}
            for s in sources:
                first.setdefault(s.paper_id, s.n)
            text = _renumber_to_sources(text, first)
        gaps = await self._validated_gaps(user_id, project_id, body.section)
        turn = build_turn(
            body.action, body.section, body.instruction, text, sources, cited_titles, gaps
        )
        out = await assistant.run(user_id, turn, str(draft_id))
        suggestion = finish(out, numbers, sources, grounded=not editing)
        known = project_ids | {p.paper_id for p in papers}
        analysed = {**cited_analysed, **{p.paper_id: p for p in papers}}
        checks = check_sentences(suggestion.text, known, analysed)
        summary = summarise(checks)
        return ResearchWritingOut(
            action=body.action,
            text=suggestion.text,
            notes=suggestion.notes,
            sources=[
                ResearchWritingSource(
                    paper_id=s.paper_id,
                    paper_title=s.title,
                    section=s.section,
                    claim_text=s.text,
                    quote=s.quote,
                )
                for s in suggestion.sources
            ],
            invalid_markers=suggestion.invalid_markers,
            checks=_checks_out(checks),
            summary=summary,
            unsupported_count=summary["unsupported"]
            + summary["citation_mismatch"]
            + summary["invalid_reference"],
        )

    async def _validated_gaps(
        self, user_id: uuid.UUID, project_id: uuid.UUID, section: str | None
    ) -> list[str]:
        if section not in ("introduction", "problem_statement", "limitations", "future_work"):
            return []
        rows = await ResearchGapRepository(self._db).all_for_project(user_id, project_id)
        return [g.title for g in rows if g.validation_status in ("accepted", "investigating")][:8]


def _renumber_to_sources(text: str, first_source: dict[uuid.UUID, int]) -> str:
    """Existing `{{cite:..}}` markers in text sent with sources become the number of that paper's
    first source; markers of papers without a source are removed (the researcher's text is not
    changed on disk, only what is sent)."""
    from app.research.drafts import CITE

    def swap(m: re.Match[str]) -> str:
        n = first_source.get(uuid.UUID(m.group(1)))
        return "" if n is None else f"[{n}]"

    return CITE.sub(swap, text)


__all__ = ["ResearchDraftService", "apply_numbers"]
